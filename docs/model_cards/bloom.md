# Bloom

## 1. 简介

### 1.1 模型描述

Bloom (BigScience Large Open-science Open-access Multilingual) 是一个开源的开放权限的自回归大语言模型(LLM)，用于对用自然语言表达的多种下游任务进行文本生成。Bloom系列模型涵盖从560M到176B的多种规模，其中176B千亿级参数的大模型的预训练基于工业级的计算机集群，在46种语言和13种编程语言的文本生成中达到比拟人类写作的SOTA效果。对于训练数据集中没有显式包括的下游任务，Bloom也可以通过指令的方式，给出令人满意的zero-shot回答。

### 1.2 仓库介绍

`Bloom` 基于 `mindformers` 实现，主要涉及的文件有：

1. 模型具体实现：`mindformers/models/bloom`

    ```text
    bloom
        ├── __init__.py
        ├── bloom_tokenizer.py      # tokenizer
        ├── bloom_config.py         # 模型配置项
        ├── bloom.py                # 模型实现
        └── layers.py               # bloom 层定义
        └── convert_weight.py       # 将huggingface ckpt转成mindfomer ckpt
    ```

2. 模型配置：`configs/bloom`

    ```text
    bloom
        ├── run_bloom_560m.yaml     # 560m 用于推理
        ├── run_bloom_7.1b.yaml     # 7.1b 用于8卡训练
        ├── run_bloom_65b.yaml      # 65b  用于96卡训练
        └── run_bloom_176b.yaml     # 176b 用于128卡训练
    ```

其中Bloom_7.1b可在单机单卡上推理，在单机8卡上训练；Bloom-65B训练至少96卡；Bloom_176B训练至少128卡。

### 1.3 环境要求

- 硬件：Ascend 910A
- MindSpore：2.0.0， 1.10.0
- MindFormers版本：dev

---
## 2. 前期准备

### 2.1 数据集制作

这里以Alpaca为例，数据大概21MB,用于调试。
首先去官方下载[alpaca_data.json文件](https://github.com/tatsu-lab/stanford_alpaca/blob/main/alpaca_data.json)
然后调用`mindformers/tools/dataset_preprocess/bloom/make_mindrecord.py`脚本将json转换成mindrecord文件。

```bash
python mindformers/tools/dataset_preprocess/bloom/make_mindrecord.py --input_dataset_file=XXX/alpaca_data.json --output_path=XXX --N=10240
```

其中`--N=10240`表示将json中的52002条数据中的前10240转换成mindrecord，`--N=-1`将转换全部json中的数据. 在执行此脚本时，对于每个prompt如下操作将被执行：

- 将问题和回答按照模板制作成prompt text;
- 使用BloomTokenizer将prompt从text转成token ids;
- 添加eos_token_id直到seq_length。

执行文本后，`--output_path`目录下将生成mindrecord文件。

### 2.2 CheckPoint转换

作为参考，这里描述CheckPoint在HuggingFace和MindSpore间的转换，在不同分布式策略间的转换。Bloom_7.1bB的推理、预训练、finetune对这部分没有依赖，可以直接跳到下一章。

#### 2.2.1 在HuggingFace和MindSpore间的转换

Mindformers可以直接通过高级接口下载转换好的560M和7.1B两种规模的ckpt,无需手动转换。其中560m的原始Checkpoint来自于huggingface的[Bloomz-560m](https://huggingface.co/bigscience/bloomz-560m)；7.1B的原始Checkpoint来自于huggingface的[Bloomz-7B1-mt](https://huggingface.co/bigscience/bloomz-7b1-mt). higgingface到mindformers的CheckPoint转换由一下命令完成。

```bash
cd mindformers/models/bloom
python convert_weight.py --n_head=xx --hidden_size=xx --torch_path=path_to_hf_bin_file_or_folder --mindspore_path=output_path
```

其中`--n_head=xx --hidden_size=xx`根据模型定义，bloom_560m的分别为16/1024; bloom_7.1b的分别为32/4096.

#### 2.2.2 在不同分布式策略间的转换

通常训练采用分布式训练，而推理采用单机单卡。所以训练后涉及ckpt从分布式策略到单机策略的切换。
策略文件会在每次训练前的图编译环节生成，保存在`mindformers/scripts/mf_parallel0/ckpt_strategy.ckpt`。在转换前，需要将每个机器上的每个rank的`ckpt_strategy.ckpt`拷贝到相同路径下， 如`./src_strategy_dir`或`./dst_strategy_dir`，再将他们合并。

```python
import mindspore as ms

# src_strategy_dir/stra0.ckpt, src_strategy_dir/stra1.ckpt ... src_strategy_dir/stra127.ckpt
ms.merge_pipeline_strategys("./src_strategy_dir", "./src_strategy.ckpt")

# dst_strategy_dir/stra0.ckpt, dst_strategy_dir/stra1.ckpt ... dst_strategy_dir/stra127.ckpt
ms.merge_pipeline_strategys("./dst_strategy_dir", "./dst_strategy.ckpt")
```

然后将checkpoint从src_strategy转换成dst_strategy。如果src_strategy或dst_strategy策略为单机单卡而非分布式，则不需要提供策略文件。

```python
import mindspore as ms
# 如果src或dst策略为单机单卡而非分布式，则不需要提供策略文件。
# src_checkpoints_dir/rank_0/xxx.ckpt, src_checkpoints_dir/rank_1/xxx.ckpt ...
ms.transform_checkpoints(
    src_checkpoints_dir,
    dst_checkpoints_dir,
    ckpt_prefix = "new_",
    src_strategy_file = "./src_strategy_file.ckpt",
    dst_strategy_file = "./dst_strategy_file.ckpt")
```

---

## 3. Bloom推理

这里以Bloom_560m和bloom_7.1b为例，介绍bloom推理。

### 3.1 基于Pipeline推理

可以通过一下两种方法实列化Bloom pipeline：`pipeline`接口或AutoClass的`from_pretrain`接口。两者都会自动从云上下载预训练的模型，存储路径：`mindformers/checkpoint_download/bloom`

- 调用pipeline接口:

```python
from mindformers import pipeline
bloom_ppl = pipeline(task='text_generation', model='bloom_560m', max_length=256)
```

- 调用AutoClass的from_pretrain接口：

```python
from mindformers import AutoModel, AutoTokenizer, TextGenerationPipeline
model = AutoModel.from_pretrained("bloom_560m")
tokenizer = AutoTokenizer.from_pretrained("bloom_560m")
bloom_ppl = TextGenerationPipeline(model, tokenizer, max_length=256)
```

实例化`bloom_ppl`之后，可以将问题传入。

``` python
result = bloom_ppl([
    "what color is the sky?",
    "Translate to English: Je t’aime."
    ])
print(result)

# expect print result
# {'text_generation_text': ['what color is the sky? blue</s>']}, {'text_generation_text': ['Translate to English: Je t’aime. I love you.</s>']}]

```

### 3.2 基于API接口推理

推理也可以用更底层的MindSpore API.

```python
import numpy as np
from mindformers import AutoTokenizer
from mindformers.models.bloom import BloomConfig, BloomLMHeadModel


# ##############################
# # bloom_560m config
# CKPT_FILE="bloom_560m"
# SEQ_LENGTH = 256
# config = BloomConfig(
#     param_init_type="float16",
#     embedding_init_type="float16",
#     checkpoint_name_or_path=CKPT_FILE,
#     max_decode_length=SEQ_LENGTH,
#     seq_length=SEQ_LENGTH,
#     hidden_size=1024,
#     num_layers=24,
#     num_heads=16,
#     hidden_dropout_rate=0.0,
#     attention_dropout_rate=0.0,
#     batch_size = 1,
#     use_past = True
#
# )
# ##############################

# 7B
CKPT_FILE = "bloom_7.1b"
# CKPT_FILE also takes absolute path to ckpt file, e.g.
# "/home/xxx/mindformers/checkpoint_download/bloom/bloom_7.1b.ckpt"
SEQ_LENGTH = 256
config = BloomConfig(
    param_init_type="float16",
    embedding_init_type="float16",
    checkpoint_name_or_path=CKPT_FILE,
    max_decode_length=SEQ_LENGTH,
    seq_length=SEQ_LENGTH,
    hidden_size=4096,
    num_layers=30,
    num_heads=32,
    hidden_dropout_rate=0.0,
    attention_dropout_rate=0.0,
    batch_size = 1,
    use_past = True
)


def chat():
    tokenizer = AutoTokenizer.from_pretrained("bloom_560m")
    model = BloomLMHeadModel(config)
    model.set_train(False)

    question_list = [
        "请问为什么说地球是独一无二的？",
        "Translate to English: Je t’aime.",
        ]


    while True:
        if question_list:
            question = question_list.pop(0)
        else:
            question = input("please input your question: ")
        inputs = tokenizer.encode(question)
        inputs = np.array([inputs]).astype(np.int32) # add batch dim
        outputs = model.generate(inputs, max_length=None, do_sample=False, eos_token_id=2)
        outputs = outputs[0] # remove batch dim
        print(tokenizer.decode(outputs))


if __name__ == "__main__":
    chat()
```

- Bloom_560m的预期输出为:

    - 请问为什么说地球是独一无二的？_**因为地球是独一无二的。</s>**_
    - Translate to English: Je t’aime. _**I love you.</s>**_

- Bloom_7.1B的预期输出为:

    - 请问为什么说地球是独一无二的？ _**地球是太阳系中唯一有生物的地方</s>**_

    - Translate to English: Je t’aime. _**I love you.</s>**_

---

> 进一步提高推理性能可以参考章节`A.2 JIT静态图推理`。

## 4. 单机8卡训练或微调

我们以单机8卡训练/微调Bloom_7.1b为例。默认配置为
|            |  SEQ | DP | MP | PP | uB | num_uB | GBS |
|------------|:----:|:--:|:--:|:--:|:--:|:------:|:---:|
| Bloom_7.1B | 2048 |  1 |  4 |  2 |  4 |    2   |  8  |

在YAML配置文件中，具体设置变量如下

- __DP__: 数据并行维度, `parallel_config.data_parallel = 1`;
- __MP__: 模型并行维度, `parallel_config.model_parallel = 4`;
- __PP__: 流水线并行维度, `parallel_config.pipeline_stage = 2`;
- __uB__: 每个microBatch大小, `runner_config.batch_size = 4`;
- __num_uB__: microBatch的数量, `parallel_config.micro_batch_num = 2`, 常稳训练时建议用16;
- __GBS__: Global Batch Size = num_uB x uB x DP.

### 4.1 生成HCCL文件

运行mindformers/tools/hccl_tools.py生成RANK_TABLE_FILE的json文件；

```shell
# step1：机器上运行如下命令，生成各自的RANK_TABLE_FILE的json文件
python ./mindformers/tools/hccl_tools.py --device_num "[0,8)"
```

若使用ModelArts的notebook环境，可从 `/user/config/jobstart_hccl.json` 路径下直接获取rank table，无需手动生成。

RANK_TABLE_FILE 单机8卡参考样例:

```json
{
    "version": "1.0",
    "server_count": "1",
    "server_list": [
        {
            "server_id": "xx.xx.xx.xx",
            "device": [
                {"device_id": "0","device_ip": "192.1.27.6","rank_id": "0"},
                {"device_id": "1","device_ip": "192.2.27.6","rank_id": "1"},
                {"device_id": "2","device_ip": "192.3.27.6","rank_id": "2"},
                {"device_id": "3","device_ip": "192.4.27.6","rank_id": "3"},
                {"device_id": "4","device_ip": "192.1.27.7","rank_id": "4"},
                {"device_id": "5","device_ip": "192.2.27.7","rank_id": "5"},
                {"device_id": "6","device_ip": "192.3.27.7","rank_id": "6"},
                {"device_id": "7","device_ip": "192.4.27.7","rank_id": "7"}],
             "host_nic_ip": "reserve"
        }
    ],
    "status": "completed"
}
```

### 4.2 启动预训练或微调

通过`/configs/bloom/run_bloom_7.1b.yaml`中的`model:checkpoint_name_or_path:`字段来控制是否加载CKPT. 请安如下方式区分预训练或者微调：
|  | pretrain | finetune |
|--------------------------------------------:  |:----------:|:----------:|
| `load_checkpoint` |     ""     | "xxx/bloom_7.1b.ckpt'"|
| `train_dataset:data_loader:dataset_dir`      | PRETRAIN_DATASET | FINETUNE_DATASET |
| 初始loss      | 12.xx | 3.xx |

其中`PRETRAIN_DATASET`和`FINETUNE_DATASET`都可以用alpaca_2049调试。

```bash
cd scripts

# pretrain
bash run_distribute.sh RANK_TABLE_FILE ../configs/bloom/run_bloom_7.1b.yaml [0,8] train 8

# finetune
bash run_distribute.sh RANK_TABLE_FILE ../configs/bloom/run_bloom_7.1b.yaml [0,8] finetune 8
```

其中RANK_TABLE_FILE为上一步生成的rank table文件。执行后，相关日志输出在`mindformers/output/log/`训练过程中保存的ckpt存在`mindformers/output/checkpoint`目录下。可以通过`tail -f ../output/log/rank_7/mindformers.log`来查看当前的训练情况。

> 备注：finetune结束后，如果需要查看推理效果，请将每个rank的ckpt，策略文件拷贝统一的ckpt路径和策略文件路径下，参考2.2.2将分布式ckpt合并用于单机推理。

## 5. 多机多卡的训练

这里以12机96卡训练65B为例。默认配置为

|            |  SEQ | DP | MP | PP | uB | num_uB | GBS |
|------------|:----:|:--:|:--:|:--:|:--:|:------:|:---:|
| Bloom_7.1B | 2048 |  2 |  4 | 12 |  1 |   48   | 96  |

在YAML配置文件中，具体设置变量如下

- __DP__: 数据并行维度, `parallel_config.data_parallel = 2`;
- __MP__: 模型并行维度, `parallel_config.model_parallel = 4`;
- __PP__: 流水线并行维度, `parallel_config.pipeline_stage = 12`;
- __uB__: 每个microBatch大小, `runner_config.batch_size = 1`;
- __num_uB__: microBatch的数量, `parallel_config.micro_batch_num = 48`, 常稳训练时建议用80;
- __GBS__: Global Batch Size=num_uB x uB x DP.

### 5.1 生成HCCL文件

- step1: 参考单机多卡启动方式，在每台机器上运行mindformers/tools/hccl_tools.py生成RANK_TABLE_FILE的json文件；

- step2: 将每台机器上生成的RANK_TABLE_FILE拷贝到一起，执行merge_hccl.py脚本将不同机器上生成的RANK_TABLE_FILE文件中的hccl*.json进行合并，包括server_list合并，server_count设为机器数，rank_id顺序增加，生成合并后的RANK_TABLE_FILE文件，

- step3: 拷贝到所有机器中，保证不同机器上的RANK_TABLE_FILE相同；

```shell
# step1：在每个机器上运行如下命令，生成各自的RANK_TABLE_FILE的json文件。
python ./mindformers/tools/hccl_tools.py --device_num "[0,8)"

# step2：运行如下命令，合并每个机器上的RANK_TABLE_FILE文件。
python ./mindformers/tools/merge_hccl.py hccl*.json

# step3：将step2得到的合并后的RANK_TABLE_FILE文件分别复制到所有的机器上。
```

### 5.2 启动预训练或微调

在每台机器上启动`bash run_distribute.sh`。

```bash
# launch ranks in the 0th server
cd scripts
bash run_distribute.sh $RANK_TABLE_FILE ../configs/bloom/run_bloom_65b.yaml [0,8] train 96

# launch ranks in the 1-11 server via ssh
for idx in {1..11}
do  
    let rank_start=8*$idx
    let rank_end=$rank_start+8
    ssh ${IP_LIST[$idx]} "cd scripts; bash run_distribute.sh $RANK_TABLE_FILE ../configs/bloom/run_bloom_65b.yaml [$rank_start,$rank_end] train 96"
done
```

其中

- `RANK_TABLE_FILE`为上一步汇总并分发的总rank table文件；
- `IP_LIST`为12台服务器的IP地址。如192.168.0.[0-11]

```bash
IP_LIST=("192.168.0.0", "192.168.0.1", ..., "192.168.0.11")
```

---

## 附录A 更多推理技巧

### A.1 模型并行推理（以1机8卡推理Bloom_7.1B为例）

这里我们以1机器8卡推理bloom_7.1B为例。涉及两个文件`chat.py`和`run_chat.py`。

```text
/SOME/PATH/
    ├── chat.py # 负责定义一个并行进程
    └── run_chat.py # 负责多次执行chat.py并拉起分布式
```

加载ckpt有两种方式, 由`run_chat.py` 中的`DISTRIBUTED_CKPT_PATH`变量来控制。这里默认使用`DISTRIBUTED_CKPT_PATH=""`代表的`Load then Shard`的方式加载ckpt.

| 分布式加载ckpt的方法   | Load then Shard | Shard then Load |
|-----------------------:|:-----------------|:-----------------|
| DISTRIBUTED_CKPT_PATH= | "" | "/path/to/distributed/ckpt/" |
|说明| 先加载全量ckpt，然后切分模型。|先切分模型，然后加载分布式ckpt。|
|| 不用预先按照策略切分ckpt，推理时可以灵活调整策略。|需要确定推理的分布式策略，并按照策略预先切分ckpt。 |
|| 对host内存的占用较高。| 对host内存的占用较低。|
|适用| 适用于较小模型，如`560m`，`7.1b`。|适用于较大模型，如`65b`, `176b`。 |

``` python
# >>> `chat.py`文件

import os
import time
import numpy as np

import mindspore as ms
from mindspore.train import Model
from mindspore import load_checkpoint, load_param_into_net
from mindspore.parallel import set_algo_parameters
from mindspore.parallel._cost_model_context import _set_multi_subgraphs

from mindformers import pipeline
from mindformers import BloomLMHeadModel, BloomConfig, AutoTokenizer
from mindformers import init_context
from mindformers.modules import TransformerOpParallelConfig
from mindformers.trainer.utils import get_last_checkpoint
from mindformers.tools import logger

SEQ_LENGTH = 256
DISTRIBUTED_CKPT_PATH = os.getenv("DISTRIBUTED_CKPT_PATH", "")


# set context
context_config = {"device_target": "Ascend", "mode": 0,  "max_device_memory": "31GB"}
parallel_context_config = {"parallel_mode": 1, "gradients_mean": False, "full_batch": True}
rank_id, device_num = init_context(use_parallel=True, context_config=context_config, parallel_config=parallel_context_config)
set_algo_parameters(elementwise_op_strategy_follow=True, fully_use_devices=True)
_set_multi_subgraphs()


# config blooom 7.1b
config = BloomConfig(
    embedding_init_type="float32" if DISTRIBUTED_CKPT_PATH else "float16",
    checkpoint_name_or_path="" if DISTRIBUTED_CKPT_PATH else "bloom_7.1b",
    seq_length=SEQ_LENGTH,
    hidden_size=4096,
    num_layers=30,
    num_heads=32,
    hidden_dropout_rate=0.0,
    attention_dropout_rate=0.0,
    top_k=1, top_p=1, do_sample=True,
    parallel_config=TransformerOpParallelConfig(
        data_parallel=1,
        model_parallel=8,
        pipeline_stage=1
        )
    )

def chat():
    # init bloom
    tokenizer = AutoTokenizer.from_pretrained("bloom_560m")
    bloom = BloomLMHeadModel(config)
    bloom.set_train(False)

    if DISTRIBUTED_CKPT_PATH:
        # find the sharded ckpt path for this rank
        ckpt_path = os.path.join(DISTRIBUTED_CKPT_PATH, "rank_{}".format(rank_id))
        ckpt_path = get_last_checkpoint(ckpt_path)
        logger.info("ckpt path: %s", str(ckpt_path))

        # shard bloom and load sharded ckpt
        m = Model(bloom)
        m.infer_predict_layout(ms.Tensor(np.ones(shape=(1, SEQ_LENGTH)), ms.int32))
        checkpoint_dict = load_checkpoint(ckpt_path)
        not_load_network_params = load_param_into_net(bloom, checkpoint_dict)
        logger.info("Network parameters are not loaded: %s", str(not_load_network_params))

    question_list = [
        "请问为什么说地球是独一无二的？",
        "Translate to English: Je t’aime.",
        ]


    for question in question_list:
        inputs = tokenizer.encode(question)
        inputs = np.array([inputs]).astype(np.int32) # add batch dim
        outputs = bloom.generate(inputs, max_length=None, do_sample=False, eos_token_id=2)
        outputs = outputs[0] # remove batch dim
        print(tokenizer.decode(outputs))


if __name__ == "__main__":
    chat()

```

```bash
# >>> `run_chat.sh`文件

# define variable
export RANK_SIZE=8
export RANK_TABLE_FILE="../hccl_8p.json" # <<< change to yours

# distributed ckpt path to load after sharding model.
# use "" if load full ckpt before sharding model.
export DISTRIBUTED_CKPT_PATH=""

export START_RANK=0 # this server start rank
export END_RANK=8 # this server end rank

# run
for((i=${START_RANK}; i<${END_RANK}; i++))
do
    export RANK_ID=$i
    export DEVICE_ID=$((i-START_RANK))
    echo "Start distribute running for rank $RANK_ID, device $DEVICE_ID"
    python3 ./chat.py &> minformers_$RANK_ID.log &
done

```

使用一下命令拉起分布式推理:

```bash
bash run_chat.sh
```

日志可以通过`tail -f mindformers_0.log`查看。预期结果与单机单卡`bloom_7.1b`推理相同：

- 请问为什么说地球是独一无二的？ _**地球是太阳系中唯一有生物的地方</s>**_

- Translate to English: Je t’aime. _**I love you.</s>**_

### A.2 JIT静态图推理

在参考章节`3.2 基于API接口推理`进行Bloom推理时，脚本实际采用了mindspore的默认动态图模式(Pynative_mode)。为了进一步提高性能，可以通过`export JIT_INFERENCE="1"`的环境变量，可以针对Bloom模型使用JIT编译提高推理性能，同时保证内存占用不超出910A单机单卡内存容量。

> 注意：由于Bloom的25万词汇量的词表较大，全局开启静态图模式`ms.set_context(mode=ms.GRAPH_MODE)`会使Bloom-7.1B在910A单卡上, seq_length=1024, batch_size=1的推理Out of Memory. 推理时, MindSpore 2.0及以上建议使用`export JIT_INFERENCE="1"`环境变量对Bloom模型进行静态编译。在seq_length=1024, batch_size=1时，Bloom-7.1B在910A单卡上的推理速度为18 tokens/s左右。

- 静态图推理

```bash
export JIT_INFERENCE="1"
```

- 动态推理或训练时

```bash
unset JIT_INFERENCE
```

### A.3 KV-Cache增量推理

> `3.2 基于API接口推理`已默认开启。

在`seq_length`较大时，可以考虑开启KV-Cache增量推理来进一步提高推理性能。开启方式是在config中添加`batch_size = 1`和`use_past = True`字段。