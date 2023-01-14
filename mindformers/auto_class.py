# Copyright 2022 Huawei Technologies Co., Ltd
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
AutoConfig、AutoModel
"""
import os
import json
import shutil
import copy

from .mindformer_book import MindFormerBook, print_dict
from .models import build_processor
from .models.base_config import BaseConfig
from .models.build_model import build_model
from .models.build_config import build_model_config
from .tools import logger
from .tools.register.config import MindFormerConfig


__all__ = ['AutoConfig', 'AutoModel', 'AutoProcessor', 'AutoTokenizer']


class AutoConfig:
    """
    AutoConfig class,
    helps instantiates a config by yaml model name or path.
    If using a model name, the config yaml will be downloaded from obs to ./checkpoint_download dir

    Examples:
        >>> from mindformers.auto_class import AutoConfig
        >>>
        >>> # 1)  instantiates a config by yaml model name
        >>> config_a = AutoConfig.from_pretrained('clip_vit_b_32')
        >>> # 2)  instantiates a config by yaml model path
        >>> from mindformers.mindformer_book import MindFormerBook
        >>> config_path = os.path.join(MindFormerBook.get_project_path(),
        ...                            'configs', 'clip', 'model_config', "clip_vit_b_32.yaml")
        >>> config_b = AutoConfig.from_pretrained(config_path)
    """
    _support_list = MindFormerBook.get_model_support_list()

    def __init__(self):
        raise EnvironmentError(
            "AutoConfig is designed to be instantiated "
            "using the `AutoConfig.from_pretrained(yaml_name_or_path)` method."
        )

    @classmethod
    def from_pretrained(cls, yaml_name_or_path):
        """
        From pretrain method, which instantiates a config by yaml model name or path.

        Args:
            yaml_name_or_path (str): A supported model name or a path to model
            config (.yaml), the supported model name could be selected from
            AutoConfig.show_support_list().

        Returns:
            A model config, which inherited from BaseConfig.
        """
        if not isinstance(yaml_name_or_path, str):
            raise TypeError(f"yaml_name_or_path should be a str,"
                            f" but got {type(yaml_name_or_path)}.")

        if os.path.exists(yaml_name_or_path):
            if not yaml_name_or_path.endswith(".yaml"):
                raise ValueError(f"{yaml_name_or_path} should be a .yaml file for model"
                                 " config.")

            config_args = MindFormerConfig(yaml_name_or_path)
            logger.info("the content in %s is used for"
                        " config building.", yaml_name_or_path)
        elif yaml_name_or_path.split('_')[0] not in cls._support_list.keys() or\
                yaml_name_or_path not in cls._support_list[yaml_name_or_path.split('_')[0]]:
            raise ValueError(f"{yaml_name_or_path} is not a supported"
                             f" model type or a valid path to model config."
                             f" supported model could be selected from {cls._support_list}.")
        else:
            checkpoint_path = os.path.join(MindFormerBook.get_default_checkpoint_download_folder(),
                                           yaml_name_or_path.split("_")[0])

            if not os.path.exists(checkpoint_path):
                os.makedirs(checkpoint_path)

            yaml_file = os.path.join(checkpoint_path, yaml_name_or_path+".yaml")
            if not os.path.exists(yaml_file):
                default_yaml_file = os.path.join(
                    MindFormerBook.get_project_path(),
                    "configs", yaml_name_or_path.split("_")[0],
                    "model_config", yaml_name_or_path + ".yaml")
                if os.path.realpath(default_yaml_file) and os.path.exists(default_yaml_file):
                    shutil.copy(default_yaml_file, yaml_file)
                    logger.info("default yaml config in %s is used.", yaml_file)
                else:
                    raise FileNotFoundError(f'default yaml file path must be correct, but get {default_yaml_file}')

            config_args = MindFormerConfig(yaml_file)

        config = build_model_config(config_args.model.model_config)
        MindFormerBook.set_model_config_to_name(id(config), config_args.model.arch.type)
        return config

    @classmethod
    def show_support_list(cls):
        """show support list method"""
        logger.info("support list of %s is:", cls.__name__)
        print_dict(cls._support_list)

    @classmethod
    def get_support_list(cls):
        """get support list method"""
        return cls._support_list


class AutoModel:
    """
    AutoModel class
    helps instantiates a model by yaml model name, path or config.
    If using a model name,
    the config yaml and checkpoint file will be downloaded from obs to ./checkpoint_download dir

    Examples:
        >>> from mindformers.auto_class import AutoModel
        >>>
        >>> # 1)  input model name, load model and weights
        >>> model_a = AutoModel.from_pretrained('clip_vit_b_32')
        >>> # 2)  input model directory, load model and weights
        >>> from mindformers.mindformer_book import MindFormerBook
        >>> checkpoint_dir = os.path.join(MindFormerBook.get_default_checkpoint_download_folder(), 'clip')
        >>> model_b = AutoModel.from_pretrained(checkpoint_dir)
        >>> # 3)  input yaml path, load model without weights
        >>> config_path = os.path.join(MindFormerBook.get_project_path(),
        ...                            'configs', 'clip', 'model_config', "clip_vit_b_32.yaml")
        >>> model_c = AutoModel.from_config(config_path)
        >>> # 4)  input config, load model without weights
        >>> config = AutoConfig.from_pretrained('clip_vit_b_32')
        >>> model_d = AutoModel.from_config(config)
    """
    _support_list = MindFormerBook.get_model_support_list()

    def __init__(self):
        raise EnvironmentError(
            "AutoModel is designed to be instantiated "
            "using the `AutoModel.from_pretrained(pretrained_model_name_or_dir)` method "
            "or `AutoModel.from_config(config)` method."
        )

    @classmethod
    def from_config(cls, config):
        """
        From config method, which instantiates a Model by config.

        Args:
            config (str, BaseConfig): A model config inherited from BaseConfig,
            or a path to .yaml file for model config.

        Returns:
            A model, which inherited from BaseModel.
        """
        if config is None:
            raise ValueError("a model cannot be built from config with config is None.")

        if isinstance(config, BaseConfig):
            inversed_config = cls._inverse_parse_config(config)
            config_args = cls._wrap_config(inversed_config)
        elif os.path.exists(config) and config.endswith(".yaml"):
            config_args = MindFormerConfig(config)
        else:
            raise ValueError("config should be inherited from BaseConfig,"
                             " or a path to .yaml file for model config.")

        model = build_model(config_args.model)
        logger.info("model built successfully!")
        return model

    @classmethod
    def _inverse_parse_config(cls, config):
        """
        Inverse parse config method, which builds yaml file content for model config.

        Args:
            config (BaseConfig): a model config inherited from BaseConfig.

        Returns:
            A model config, which follows the yaml content.
        """
        if not isinstance(config, BaseConfig):
            return config

        class_name = config.__class__.__name__
        config.update({"type": class_name})

        for key, val in config.items():
            new_val = cls._inverse_parse_config(val)
            config.update({key: new_val})

        return config

    @classmethod
    def _wrap_config(cls, config):
        """
        Wrap config function, which wraps a config to rebuild content of yaml file.

        Args:
            config (BaseConfig): a config processed by _inverse_parse_config function.

        Returns:
            A model config, which has the same content as a yaml file.
        """
        model_name = config.pop("model_name", None)
        if model_name is None:
            model_name = MindFormerBook.get_model_config_to_name().get(id(config), None)

        arch = BaseConfig(type=model_name)
        model = BaseConfig(model_config=config, arch=arch)
        return BaseConfig(model=model)

    @classmethod
    def from_pretrained(cls, pretrained_model_name_or_dir):
        """
        From pretrain method, which instantiates a Model by pretrained model name or path.

        Args:
            pretrained_model_name_or_path (str): A supported model name or a
            directory to model checkpoint (including .yaml file for config
            and .ckpt file for weights), the supported model name could be
            selected from AutoModel.show_support_list().

        Returns:
            A model, which inherited from BaseModel.
        """
        if not isinstance(pretrained_model_name_or_dir, str):
            raise TypeError(f"pretrained_model_name_or_dir should be a str,"
                            f" but got {type(pretrained_model_name_or_dir)}")

        is_exist = os.path.exists(pretrained_model_name_or_dir)
        is_dir = os.path.isdir(pretrained_model_name_or_dir)

        if is_exist:
            if not is_dir:
                raise ValueError(f"{pretrained_model_name_or_dir} is not a directory.")
        else:
            model_type = pretrained_model_name_or_dir.split('_')[0]
            if model_type not in cls._support_list.keys() or pretrained_model_name_or_dir \
                    not in cls._support_list[model_type]:
                raise ValueError(f"{pretrained_model_name_or_dir} is not a supported model"
                                 f" type or a valid path to model config. supported model"
                                 f" could be selected from {cls._support_list}.")

        if is_dir:
            yaml_list = [file for file in os.listdir(pretrained_model_name_or_dir)
                         if file.endswith(".yaml")]
            ckpt_list = [file for file in os.listdir(pretrained_model_name_or_dir)
                         if file.endswith(".ckpt")]
            if not yaml_list or not ckpt_list:
                raise FileNotFoundError(f"there is no yaml file for model config or ckpt file"
                                        f" for model weights in {pretrained_model_name_or_dir}")

            yaml_file = os.path.join(pretrained_model_name_or_dir, yaml_list[0])
            ckpt_file = os.path.join(pretrained_model_name_or_dir, ckpt_list[0])
            logger.info("config in %s and weights in %s are used for model"
                        " building.", yaml_file, ckpt_file)

            config_args = MindFormerConfig(yaml_file)
            config_args.model.model_config.update({"checkpoint_name_or_path": ckpt_file})
            model = build_model(config_args.model)
        else:
            checkpoint_path = os.path.join(MindFormerBook.get_default_checkpoint_download_folder(),
                                           pretrained_model_name_or_dir.split("_")[0])
            if not os.path.exists(checkpoint_path):
                os.makedirs(checkpoint_path)

            yaml_file = os.path.join(checkpoint_path, pretrained_model_name_or_dir+".yaml")

            if not os.path.exists(yaml_file):
                default_yaml_file = os.path.join(
                    MindFormerBook.get_project_path(),
                    "configs", pretrained_model_name_or_dir.split("_")[0],
                    "model_config", pretrained_model_name_or_dir + ".yaml")
                if os.path.realpath(default_yaml_file) and os.path.exists(default_yaml_file):
                    shutil.copy(default_yaml_file, yaml_file)
                    logger.info("default yaml config in %s is used.", yaml_file)
                else:
                    raise FileNotFoundError(f'default yaml file path must be correct, but get {default_yaml_file}')

            config_args = MindFormerConfig(yaml_file)
            config_args.model.model_config.update(
                {"checkpoint_name_or_path": pretrained_model_name_or_dir})
            model = build_model(config_args.model)
        logger.info("model built successfully!")
        return model

    @classmethod
    def show_support_list(cls):
        """show support list method"""
        logger.info("support list of %s is:", cls.__name__)
        print_dict(cls._support_list)

    @classmethod
    def get_support_list(cls):
        """get support list method"""
        return cls._support_list


class AutoProcessor:
    """
    AutoProcessor
    helps instantiates a processor by yaml model name or path.
    If using a model name, the config yaml will be downloaded from obs to ./checkpoint_download dir

    Examples:
        >>> from mindformers.auto_class import AutoProcessor
        >>>
        >>> # 1)  instantiates a processor by yaml model name
        >>> pro_a = AutoProcessor.from_pretrained('clip_vit_b_32')
        >>> # 2)  instantiates a processor by yaml model path
        >>> from mindformers.mindformer_book import MindFormerBook
        >>> config_path = os.path.join(MindFormerBook.get_project_path(),
        ...                            'configs', 'clip', 'model_config', "clip_vit_b_32.yaml")
        >>> pro_b = AutoProcessor.from_pretrained(config_path)
    """
    _support_list = copy.deepcopy(MindFormerBook.get_model_support_list())
    _support_list.pop("mae")

    def __init__(self):
        raise EnvironmentError(
            "AutoProcessor is designed to be instantiated "
            "using the `AutoProcessor.from_pretrained(yaml_name_or_path)` method."
        )

    @classmethod
    def from_pretrained(cls, yaml_name_or_path):
        """
        From pretrain method, which instantiated a processor by yaml name or path.

        Args:
            yaml_name_or_path (str): A supported yaml name or a path to .yaml file,
            the supported model name could be selected from .show_support_list().

        Returns:
            A processor which inherited from BaseProcessor.
        """
        if not isinstance(yaml_name_or_path, str):
            raise TypeError(f"yaml_name_or_path should be a str,"
                            f" but got {type(yaml_name_or_path)}")

        is_exist = os.path.exists(yaml_name_or_path)
        model_name = yaml_name_or_path.split("_")[0]
        if not is_exist and model_name not in cls._support_list.keys():
            raise ValueError(f'{yaml_name_or_path} does not exist,'
                             f' and it is not supported by {cls.__name__}. '
                             f'please select from {cls._support_list}.')

        if is_exist:
            logger.info("config in %s is used for auto processor"
                        " building.", yaml_name_or_path)
            if os.path.isdir(yaml_name_or_path):
                yaml_list = [file for file in os.listdir(yaml_name_or_path) if file.endswith(".yaml")]
                yaml_name = os.path.join(yaml_name_or_path, yaml_list[0])
                config_args = MindFormerConfig(yaml_name)
            else:
                config_args = MindFormerConfig(yaml_name_or_path)
        else:
            if model_name in cls._support_list.keys() and \
                    yaml_name_or_path in cls._support_list[model_name]:
                checkpoint_path = os.path.join(
                    MindFormerBook.get_default_checkpoint_download_folder(),
                    model_name)
            else:
                raise ValueError(f'{yaml_name_or_path} does not exist,'
                                 f' or it is not supported by {cls.__name__}.'
                                 f' please select from {cls._support_list}.')

            if not os.path.exists(checkpoint_path):
                os.makedirs(checkpoint_path)

            yaml_file = os.path.join(checkpoint_path, yaml_name_or_path + ".yaml")
            if not os.path.exists(yaml_file):
                default_yaml_file = os.path.join(
                    MindFormerBook.get_project_path(),
                    "configs", yaml_name_or_path.split("_")[0],
                    "model_config", yaml_name_or_path + ".yaml")
                if os.path.realpath(default_yaml_file) and os.path.exists(default_yaml_file):
                    shutil.copy(default_yaml_file, yaml_file)
                    logger.info("default yaml config in %s is used.", yaml_file)
                else:
                    raise FileNotFoundError(f'default yaml file path must be correct, but get {default_yaml_file}')

            config_args = MindFormerConfig(yaml_file)

        lib_path = yaml_name_or_path
        if not os.path.isdir(lib_path):
            lib_path = None
        processor = build_processor(config_args.processor, lib_path=lib_path)
        logger.info("processor built successfully!")
        return processor

    @classmethod
    def show_support_list(cls):
        """show support list method"""
        logger.info("support list of %s is:", cls.__name__)
        print_dict(cls._support_list)

    @classmethod
    def get_support_list(cls):
        """get support list method"""
        return cls._support_list


class AutoTokenizer:
    """
    Load the tokenizer according to the `yaml_name_or_path`. It supports the following situations
    1. `yaml_name_or_path` is the model name.
    2. `yaml_name_or_path` is the path to the downloaded files.

    Examples:
        >>> from mindformers.auto_class import AutoTokenizer
        >>>
        >>> # 1)  instantiates a tokenizer by the model name
        >>> tokenizer_a = AutoTokenizer.from_pretrained("clip_vit_b_32")
        >>> # 2)  instantiates a tokenizer by the path to the downloaded files.
        >>> from mindformers.models.clip.clip_tokenizer import ClipTokenizer
        >>> clip_tokenizer = ClipTokenizer.from_pretrained("clip_vit_b_32")
        >>> clip_tokenizer.save_pretrained(path_saved)
        >>> restore_tokenizer = AutoTokenizer.from_pretrained(path_saved)
    """
    _support_list = MindFormerBook.get_tokenizer_support_list()

    @classmethod
    def _get_class_name_from_yaml(cls, yaml_name_or_path):
        """
        Try to find the yaml from the given path
        Args:
            yaml_name_or_path (str): the directory of the config yaml

        Returns:
            The class name of the tokenizer in the config yaml.
        """
        is_exist = os.path.exists(yaml_name_or_path)
        is_dir = os.path.isdir(yaml_name_or_path)
        is_file = os.path.isfile(yaml_name_or_path)
        if not is_file:
            if not is_exist:
                raise ValueError(f"{yaml_name_or_path} does not exist, Please pass a valid the directory.")
            if not is_dir:
                raise ValueError(f"{yaml_name_or_path} is not a directory. You should pass the directory.")
            # If passed a directory, load the file from the yaml files
            yaml_list = [file for file in os.listdir(yaml_name_or_path) if file.endswith(".yaml")]
            if not yaml_list:
                return None
            yaml_file = os.path.join(yaml_name_or_path, yaml_list[0])
        else:
            yaml_file = yaml_name_or_path
        logger.info("Config in the yaml file %s are used for tokenizer building.", yaml_file)
        config = MindFormerConfig(yaml_file)

        class_name = None
        if config and 'processor' in config and 'tokenizer' in config['processor'] \
                and 'type' in config['processor']['tokenizer']:
            class_name = config['processor']['tokenizer'].pop('type', None)
            logger.info("Load the tokenizer name %s from the %s", class_name, yaml_name_or_path)

        return class_name

    @classmethod
    def _get_class_name_from_tokenizer_config_file(cls, yaml_name_or_path):
        """
        try to get the tokenizer type from tokenizer_config.json
        Args:
            yaml_name_or_path (str): the directory of tokenizer_config.json

        Returns:
            The class name of the tokenizer in tokenizer_config.json
        """
        tokenizer_config_path = os.path.join(yaml_name_or_path, 'tokenizer_config.json')
        if not os.path.exists(tokenizer_config_path):
            raise FileNotFoundError(f"The file `tokenizer_config.json` should exits in the "
                                    f"path {tokenizer_config_path}, but not found.")
        with open(tokenizer_config_path, 'r') as fp:
            config_kwargs = json.load(fp)
        class_name = config_kwargs.pop('tokenizer_class', None)
        if not class_name:
            raise ValueError(f"There should be the key word`tokenizer_class` in {tokenizer_config_path}, but "
                             f"not found. The optional keys are {config_kwargs.keys()}")
        return class_name

    @classmethod
    def from_pretrained(cls, yaml_name_or_path):
        """
        From pretrain method, which instantiates a tokenizer by yaml name or path.

        Args:
            yaml_name_or_path (str): A supported yaml name or a path to .yaml file,
            the supported model name could be selected from .show_support_list().

        Returns:
            A tokenizer which inherited from PretrainedTokenizer.
        """
        from . import MindFormerRegister
        if not isinstance(yaml_name_or_path, str):
            raise TypeError(f"yaml_name_or_path should be a str,"
                            f" but got {type(yaml_name_or_path)}")
        # Try to load from the remote
        if yaml_name_or_path in sum(cls._support_list.values(), []):
            # Should download the files from the remote storage
            checkpoint_path = os.path.join(MindFormerBook.get_default_checkpoint_download_folder(),
                                           yaml_name_or_path.split("_")[0])
            if not os.path.exists(checkpoint_path):
                os.makedirs(checkpoint_path)

            yaml_file = os.path.join(checkpoint_path, yaml_name_or_path+".yaml")
            if not os.path.exists(yaml_file):
                default_yaml_file = os.path.join(
                    MindFormerBook.get_project_path(),
                    "configs", yaml_name_or_path.split("_")[0],
                    "model_config", yaml_name_or_path + ".yaml")
                if os.path.realpath(default_yaml_file) and os.path.exists(default_yaml_file):
                    shutil.copy(default_yaml_file, yaml_file)
                    logger.info("default yaml config in %s is used.", yaml_file)
                else:
                    raise FileNotFoundError(f'default yaml file path must be correct, but get {default_yaml_file}')
            class_name = cls._get_class_name_from_yaml(yaml_file)
        elif os.path.isdir(yaml_name_or_path):
            class_name = cls._get_class_name_from_yaml(yaml_name_or_path)
            if not class_name:
                class_name = cls._get_class_name_from_tokenizer_config_file(yaml_name_or_path)
        else:
            raise FileNotFoundError(f"{yaml_name_or_path} does not exist. "
                                    f"You can select one from {cls._support_list.keys()}."
                                    f"Or make sure the {yaml_name_or_path} is a directory.")

        dynamic_class = MindFormerRegister.get_cls(module_type='tokenizer', class_name=class_name)
        instanced_class = dynamic_class.from_pretrained(yaml_name_or_path)
        logger.info("%s Tokenizer built successfully!", instanced_class.__class__.__name__)
        return instanced_class

    @classmethod
    def show_support_list(cls):
        """show support list method"""
        logger.info("support list of %s is:", cls.__name__)
        print_dict(cls._support_list)

    @classmethod
    def get_support_list(cls):
        """get support list method"""
        return cls._support_list
