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

"""
Test module for testing the bloom interface used for mindformers.
How to run this:
pytest tests/st/test_model/test_bloom_model/test_autoclass.py
"""
import os
import pytest

import mindspore as ms

from mindformers import MindFormerBook, AutoModel, AutoConfig, AutoTokenizer, AutoProcessor
from mindformers.models import BaseModel, BaseConfig, BaseTokenizer, BaseProcessor

ms.set_context(mode=0)


@pytest.mark.level0
@pytest.mark.platform_x86_ascend_training
@pytest.mark.platform_arm_ascend_training
@pytest.mark.env_onecard
class TestBloomAutoClassMethod:
    """A test class for testing Model classes"""

    def setup_method(self):
        """setup method."""
        self.save_directory = os.path.join(MindFormerBook.get_project_path(), 'checkpoint_save')
        self.test_llm_list = ['bloom_560m']

    @pytest.mark.run(order=1)
    def test_llm_model(self):
        """
        Feature: AutoModel.
        Description: Test to get LL-Model instance by input model type.
        Expectation: TypeError, ValueError, RuntimeError
        """
        # input model name, load model and weights
        for model_type in self.test_llm_list:
            model = AutoModel.from_pretrained(model_type)
            assert isinstance(model, BaseModel)
            model.save_pretrained(
                save_directory=os.path.join(self.save_directory, model_type),
                save_name=model_type + '_model')

    @pytest.mark.run(order=2)
    def test_llm_config(self):
        """
        Feature: AutoConfig.
        Description: Test to get config instance by input config type.
        Expectation: TypeError, ValueError, RuntimeError
        """
        # input model config name, load model and weights
        for config_type in self.test_llm_list:
            model_config = AutoConfig.from_pretrained(config_type)
            assert isinstance(model_config, BaseConfig)
            model_config.save_pretrained(
                save_directory=os.path.join(self.save_directory, config_type),
                save_name=config_type + '_config')

    @pytest.mark.run(order=3)
    def test_llm_processor(self):
        """
        Feature: AutoConfig.
        Description: Test to get config instance by input config type.
        Expectation: TypeError, ValueError, RuntimeError
        """
        # input processor name
        for processor_type in self.test_llm_list:
            processor = AutoProcessor.from_pretrained(processor_type)
            assert isinstance(processor, BaseProcessor)
            processor.save_pretrained(
                save_directory=os.path.join(self.save_directory, processor_type),
                save_name=processor_type + '_processor')

    @pytest.mark.run(order=4)
    def test_llm_tokenizer(self):
        """
        Feature: AutoTokenizer, input config.
        Description: Test to get tokenizer instance by input tokenizer type.
        Expectation: TypeError, ValueError, RuntimeError
        """
        # input processor name
        for tokenizer_type in self.test_llm_list:
            tokenizer = AutoTokenizer.from_pretrained(tokenizer_type)
            assert isinstance(tokenizer, BaseTokenizer)
            tokenizer.save_pretrained(
                save_directory=os.path.join(self.save_directory, tokenizer_type),
                save_name=tokenizer_type + '_tokenizer')
