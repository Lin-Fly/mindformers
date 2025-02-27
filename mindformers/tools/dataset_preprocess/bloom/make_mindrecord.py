# Copyright 2020 Huawei Technologies Co., Ltd
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
"""generate mindrecord script"""
import os
import argparse
import collections
import json
import numpy as np
from tqdm import tqdm
from mindspore.mindrecord import FileWriter
from mindformers import AutoTokenizer


class AlpacaDatasetMaker:
    """
    AlpacaDatasetMaker
    """
    def __init__(self, input_dataset_file, output_dataset_file, seq_length):
        self.input_dataset_file = input_dataset_file
        self.output_dataset_file = output_dataset_file
        self.seq_length = seq_length

        self.tokenizer = AutoTokenizer.from_pretrained("bloom_560m")
        self.eos_token_id = self.tokenizer.eos_token_id
        self.pad_token_id = self.tokenizer.pad_token_id

        self.prompt_with_input = (
            "Below is an instruction that describes a task, paired with an input that provides further context. "
            "Write a response that appropriately completes the request.\n\n"
            "### Instruction:\n{instruction}\n\n### Input:\n{input}\n\n### Response:\n{output}"
        )
        self.prompt_without_input = (
            "Below is an instruction that describes a task. "
            "Write a response that appropriately completes the request.\n\n"
            "### Instruction:\n{instruction}\n\n### Response:\n{output}"
        )

    def make(self, num_of_prompts):
        """make mindrecord"""
        writer = FileWriter(self.output_dataset_file, 1)
        writer.add_schema(
            {"input_ids": {"type": "int64", "shape": [-1]}}, 'lm-schema')

        with open(self.input_dataset_file) as ds:
            dataset = json.load(ds)

        num_of_prompts = min(num_of_prompts, len(dataset)) if num_of_prompts > 0 else len(dataset)
        for i in tqdm(range(num_of_prompts)):
            prompt = dataset[i]
            prompt_ids = self.make_prompt_ids(prompt)

            features = collections.OrderedDict()
            features["input_ids"] = np.asarray(prompt_ids)
            writer.write_raw_data([features])

        writer.commit()

    def make_prompt_ids(self, prompt):
        """make prompt dict into ids"""
        if 'input' in prompt:
            text = self.prompt_with_input.format_map(prompt)
        else:
            text = self.prompt_without_input.format_map(prompt)

        prompt_ids = self.tokenizer(text)["input_ids"]
        if len(prompt_ids) > self.seq_length:
            prompt_ids = prompt_ids[:self.seq_length]

        self._add_eos_token_id(prompt_ids)
        self._add_pad_token_id(prompt_ids)
        return prompt_ids

    def _add_eos_token_id(self, prompt_ids):
        if len(prompt_ids) < self.seq_length:
            prompt_ids.append(self.eos_token_id)

    def _add_pad_token_id(self, prompt_ids):
        if len(prompt_ids) < self.seq_length:
            # pad eos instead of pad
            prompt_ids += [self.eos_token_id] * \
                (self.seq_length - len(prompt_ids))


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dataset_file", type=str,
                        default="/home/work/czh/data/alpaca_data.json")
    parser.add_argument("--output_path", type=str,
                        default="/home/work/czh/data/alpaca_2049/")
    parser.add_argument("--seq_length", type=int, default=2049)
    parser.add_argument("--N", type=int, default=-1)
    args = parser.parse_args()

    if args.output_path and not os.path.exists(args.output_path):
        os.makedirs(args.output_path, exist_ok=True)
    args.output_dataset_file = os.path.join(
        args.output_path, "dataset.mindrecord")

    maker = AlpacaDatasetMaker(
        args.input_dataset_file, args.output_dataset_file, args.seq_length)
    maker.make(args.N)
