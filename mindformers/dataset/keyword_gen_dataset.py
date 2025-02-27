# Copyright 2023 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Keyword Generation Dataset."""
import copy
import os

import mindspore
import mindspore.common.dtype as mstype
import mindspore.dataset.transforms.c_transforms as C
import numpy as np

from mindformers.dataset.base_dataset import BaseDataset
from mindformers.dataset.dataloader import build_dataset_loader
from mindformers.models.build_tokenizer import build_tokenizer
from mindformers.tools.logger import logger
from mindformers.tools.register import MindFormerModuleType, MindFormerRegister
from mindformers.tools.utils import is_version_ge


@MindFormerRegister.register(MindFormerModuleType.DATASET)
class KeyWordGenDataset(BaseDataset):
    """Keyword generation dataset.

    Examples:
        >>> from mindformers.dataset.dataloader.adgen_dataloader import ADGenDataLoader
        >>> from mindformers.dataset import build_dataset
        >>> from mindformers import MindFormerConfig
        >>> cfg = MindFormerConfig("./configs/glm/run_glm_6b_finetune.yaml")
        >>> dataset = build_dataset(cfg.eval_dataset_task)
        >>> for item in dataset.create_dict_iterator():
        >>>     print(item)
        >>>     break
    """

    def __new__(cls, dataset_config: dict = None):
        logger.info("Now Create Keyword Generation Dataset.")
        cls.init_dataset_config(dataset_config)
        cls.tokenizer = build_tokenizer(dataset_config.tokenizer)
        cls.ignore_pad_token_for_loss = dataset_config.ignore_pad_token_for_loss
        cls.max_source_length = dataset_config.max_source_length
        cls.max_target_length = dataset_config.max_target_length
        cls.max_seq_length = cls.max_source_length + cls.max_target_length

        cls.phase = dataset_config.data_loader.phase

        if dataset_config.data_loader.type != 'MindDataset':
            dataset = cls._process_raw_text_data(dataset_config)
        else:
            dataset = cls._process_mindrecord_data(dataset_config)

        dataset = dataset.batch(dataset_config.batch_size,
                                drop_remainder=dataset_config.drop_remainder,
                                num_parallel_workers=dataset_config.num_parallel_workers)
        dataset = dataset.repeat(dataset_config.repeat)
        type_cast_op = C.TypeCast(mstype.int32)
        for input_arg in dataset_config.input_columns:
            dataset = dataset.map(operations=type_cast_op, input_columns=input_arg)
        return dataset

    @classmethod
    def _tokenizer_map(cls, dataset, tokenizer_config):
        """Maps the tokenizer on the source and the output"""

        phase = cls.phase
        logger.info("Start tokenize on the dataset using tokenizer: %s", tokenizer_config)

        input_columns = ["prompt", "answer"]
        train_output_columns = ["input_ids", "label", "position_ids", "attention_mask"]
        eval_output_columns = ["input_ids", "label"]

        if is_version_ge(mindspore.__version__, "2.0.0"):
            if phase == "train":
                dataset = dataset.map(cls.train_dataset_function,
                                      input_columns=input_columns,
                                      output_columns=train_output_columns)
                dataset = dataset.project(columns=train_output_columns)
            if phase == "eval":
                dataset = dataset.map(cls.eval_dataset_function,
                                      input_columns=input_columns,
                                      output_columns=eval_output_columns)
                dataset = dataset.project(columns=eval_output_columns)

        else:
            if phase == "train":
                dataset = dataset.map(cls.train_dataset_function,
                                      input_columns=input_columns,
                                      output_columns=train_output_columns,
                                      column_order=train_output_columns)
            if phase == "eval":
                dataset = dataset.map(cls.eval_dataset_function,
                                      input_columns=input_columns,
                                      output_columns=eval_output_columns,
                                      column_order=eval_output_columns)
        return dataset

    @classmethod
    def _process_raw_text_data(cls, dataset_config):
        """Process the text data"""
        rank_id = int(os.getenv("RANK_ID", "0"))
        device_num = int(os.getenv("RANK_SIZE", "1"))
        dataset_dir = dataset_config.data_loader.pop("dataset_dir")
        dataset = build_dataset_loader(
            dataset_config.data_loader, default_args={'dataset_dir': dataset_dir,
                                                      'num_shards': device_num, 'shard_id': rank_id})

        dataset = cls._tokenizer_map(dataset, dataset_config.tokenizer)
        return dataset

    @classmethod
    def _process_mindrecord_data(cls, dataset_config):
        """Process the mindrecord data"""
        rank_id = int(os.getenv("RANK_ID", "0"))
        device_num = int(os.getenv("RANK_SIZE", "1"))
        dataset_config = copy.deepcopy(dataset_config)

        dataset_files = []
        if dataset_config.data_loader.dataset_dir:
            data_dir = dataset_config.data_loader.pop("dataset_dir")
            if os.path.isdir(data_dir):
                for r, _, f in os.walk(data_dir):
                    for file in f:
                        if file.endswith(".mindrecord"):
                            dataset_files.append(os.path.join(r, file))
                dataset_files.sort()
            else:
                if data_dir.endswith(".mindrecord"):
                    dataset_files = data_dir
        elif dataset_config.data_loader.dataset_files:
            dataset_files = dataset_config.data_loader.dataset_files
            if isinstance(dataset_files, (list, tuple)):
                dataset_files = list(dataset_files)
        else:
            raise ValueError(f"data_loader must contain dataset_dir or dataset_files,"
                             f"but get {dataset_config.data_loader}.")

        logger.info("Using args %s to instance the dataset.", dataset_config.data_loader)
        dataset = build_dataset_loader(
            dataset_config.data_loader, default_args={'dataset_files': dataset_files,
                                                      'num_shards': device_num, 'shard_id': rank_id,
                                                      'columns_list': dataset_config.input_columns})
        return dataset

    @classmethod
    def train_dataset_function(cls, prompt, answer):
        """generates train dataset"""
        prompt, answer = prompt.tolist(), answer.tolist()
        prompt_ids = cls.tokenizer.encode(text=prompt, add_special_tokens=False)
        answer_ids = cls.tokenizer.encode(text=answer, add_special_tokens=False)

        if len(prompt_ids) > cls.max_source_length - 1:
            prompt_ids = prompt_ids[: cls.max_source_length - 1]

        if len(answer_ids) > cls.max_target_length - 2:
            answer_ids = answer_ids[: cls.max_target_length - 2]

        input_ids = cls.tokenizer.build_inputs_with_special_tokens(prompt_ids, answer_ids)
        context_length = input_ids.index(cls.tokenizer.bos_token_id)
        mask_position = context_length - 1
        label = [-100] * context_length + input_ids[mask_position + 2:]  # +1 for logits shift

        pad_len = cls.max_seq_length - len(input_ids)
        input_ids = input_ids + [cls.tokenizer.pad_token_id] * pad_len
        label = label + [cls.tokenizer.pad_token_id] * (pad_len + 1)  # +1 for logits shift
        if cls.ignore_pad_token_for_loss:
            label = [(l if l != cls.tokenizer.pad_token_id else -100) for l in label]

        position_ids = cls.create_position_ids(np.array(input_ids))
        attention_mask = cls.get_masks(np.array(input_ids))

        return input_ids, label, position_ids, attention_mask

    @classmethod
    def eval_dataset_function(cls, prompt, answer):
        """generates eval dataset"""
        prompt, answer = prompt.tolist(), answer.tolist()
        if len(prompt) > cls.max_source_length - 2:
            prompt = prompt[: cls.max_source_length - 2]

        if len(answer) > cls.max_target_length - 2:
            answer = answer[: cls.max_target_length - 2]

        input_ids = cls.tokenizer.encode(text=prompt, add_special_tokens=True)
        label = cls.tokenizer.encode(text=answer, add_special_tokens=True)

        pad_len = cls.max_source_length - len(input_ids)
        input_ids = input_ids + [cls.tokenizer.pad_token_id] * pad_len

        return input_ids, label

    @classmethod
    def get_masks(cls, input_ids, bos_token_id=130004):
        """generate mask from input id"""

        seq_length = input_ids.shape[0]

        mask = bos_token_id * np.ones(shape=(seq_length), dtype=np.int32)
        mask = np.equal(input_ids, mask)
        # 要求input_ids中有且仅有一个bos_token_id
        context_lengths = np.argwhere(mask)[:, -1]

        attention_mask = np.tril(np.ones((seq_length, seq_length), dtype=np.float32))
        for context_length in context_lengths:
            attention_mask[:, :context_length] = 1

        attention_mask = np.logical_not(attention_mask.astype(np.bool_))
        attention_mask = attention_mask.astype(np.float32)
        attention_mask = np.expand_dims(attention_mask, 0)
        return attention_mask

    @classmethod
    def get_position_ids(cls, input_ids, mask_positions, use_gmasks=None,
                         bos_token_id=130004, position_encoding_2d=True):
        """generate position ids from input id and mask positions"""

        seq_length = input_ids.shape[0]
        if use_gmasks is None:
            use_gmasks = [False]
        mask = bos_token_id * np.ones(shape=(seq_length), dtype=np.int32)
        mask = np.equal(input_ids, mask)
        # 要求input_ids中有且仅有一个bos_token_id
        context_lengths = np.argwhere(mask)[:, -1]
        if position_encoding_2d:
            position_ids = np.arange(seq_length, dtype=np.int64)
            for i, context_length in enumerate(context_lengths):
                position_ids[context_length:] = mask_positions[i]
            block_position_ids = [np.concatenate((
                np.zeros(context_length, dtype=np.int64),
                np.arange(seq_length - context_length, dtype=np.int64) + 1
            )) for context_length in context_lengths]
            block_position_ids = np.stack(block_position_ids, axis=0).squeeze()
            position_ids = np.stack((position_ids, block_position_ids), axis=0)
        else:
            position_ids = np.arange(seq_length, dtype=np.int64)
            for i, context_length in enumerate(context_lengths):
                if not use_gmasks[i]:
                    position_ids[context_length:] = mask_positions[i]
        return position_ids

    @classmethod
    def create_position_ids(cls, input_ids, gmask_token_id=130001):
        """generate position ids from input id"""

        seq_length = input_ids.shape[0]
        seqs = input_ids
        # 要求input_ids中, 每行有且仅有一个gMASK
        use_gmasks = gmask_token_id * np.ones(shape=(seq_length), dtype=np.int32)
        mask = np.equal(seqs, use_gmasks)
        mask_positions = np.argwhere(mask)[:, -1]

        position_ids = cls.get_position_ids(input_ids, mask_positions=mask_positions, use_gmasks=use_gmasks)
        return position_ids
