import os
import uuid
from glob import glob
import datetime

from pathlib import Path

from promptify.utils.file_utils import *
from promptify.utils.conversation_utils import *
from promptify.utils.data_utils import *

from typing import List, Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader, meta, Template


class Prompter:
    """
    A class to generate prompts and obtain completions from a language model.
    Parameters
    ----------
    model : any
        A language model to generate text from.

    allowed_missing_variables : list of str, optional
        A list of variable names that are allowed to be missing from the template. Default is ['examples', 'description', 'output_format'].
    default_variable_values : dict of str: any, optional
        A dictionary mapping variable names to default values to be used in the template.
        If a variable is not found in the input dictionary or in the default values, it will be assumed to be required and an error will be raised. Default is an empty dictionary.
    max_completion_length : int, optional
        The maximum length of completions generated by the model. Default is 20.
    cache_prompt : bool, optional
        A flag indicating whether to cache prompt-completion pairs. Default is False.
    language : str, optional
        The language of the templates to be loaded. Default is 'en'.

    Methods
    -------
    get_available_templates(template_path: str) -> Dict[str, str]:
        Returns a dictionary of available templates in a directory.

    update_default_variable_values(new_defaults: Dict[str, Any]) -> None:
        Updates the default variable values with the given dictionary.

    load_multiple_templates(templates: List) -> dict:
        Loads multiple templates from a list and returns a dictionary containing their information.

    load_template(template: str) -> dict:
        Loads a single template and returns its information as a dictionary.

    verify_template_path(templates_path: str) -> None:
        Raises an error if a given template path does not exist.

    list_templates(environment) -> List[str]:
        Returns a list of available templates.

    get_multiple_template_variables(dict_templates: dict) -> dict:
        Returns a dictionary of variables for multiple templates.

    get_template_variables(environment, template_name) -> List[str]:
        Returns a list of variables in a template.

    generate_prompt(text_input, **kwargs) -> str:
        Generates a prompt from a template and input values.

    raw_fit(prompt: str) -> List[str]:
        Returns raw outputs from the model for a given prompt.

    fit(text_input, **kwargs) -> List[str]:
        Returns model outputs for a given prompt.

    """

    def __init__(
        self,
        model,
        allowed_missing_variables: Optional[List[str]] = None,
        default_variable_values: Optional[Dict[str, Any]] = None,
        max_completion_length: int = 20,
        cache_prompt: bool = False,
    ) -> None:
        """
        Initialize Prompter with default or user-specified settings.

        Parameters
        ----------
        model : any
            A language model to generate text from.
        template : str, optional
            A Jinja2 template to use for generating the prompt. Must be a valid file path.
        raw_prompt : bool, optional
            A flag indicating whether to use raw prompts or not. Default is False.
        allowed_missing_variables : list of str, optional
            A list of variable names that are allowed to be missing from the template. Default is ['examples', 'description', 'output_format'].
        default_variable_values : dict of str: any, optional
            A dictionary mapping variable names to default values to be used in the template.
            If a variable is not found in the input dictionary or in the default values, it will be assumed to be required and an error will be raised. Default is an empty dictionary.
        max_completion_length : int, optional
            The maximum length of completions generated by the model. Default is 20.
        cache_prompt : bool, optional
            A flag indicating whether to cache prompt-completion pairs. Default is False.
        language : str, optional
            The language of the templates to be loaded. Default is 'en'.
        """

        self.model = model
        self.max_completion_length = max_completion_length
        self.cache_prompt = cache_prompt
        self.prompt_cache = {}
        self.loaded_templates = {}

        self.allowed_missing_variables = [
            "examples",
            "description",
            "output_format",
        ]
        
        self.allowed_missing_variables.extend(allowed_missing_variables or [])

        self.default_variable_values = default_variable_values or {}
        self.model_args_count = self.model.run.__code__.co_argcount
        self.model_variables = self.model.run.__code__.co_varnames[
            1 : self.model_args_count
        ]
        self.prompt_variables_map = {}
        
        self.conversation_path = os.getcwd()
        self.con_folder, self.conversation_id   = setup_folder(self.conversation_path)
        self.full_path         = os.path.join(self.conversation_path, self.con_folder)
        model_dict             = {key: value for key, value in model.__dict__.items() if is_string_or_digit(value)}
        self.conversation      = get_conversation_schema(self.conversation_id, self.model.model, **model_dict)
        write_json(self.full_path, self.conversation, 'history')


    def get_available_templates(self, template_path: str) -> Dict[str, str]:
        """
        Returns a dictionary of available templates in a directory.

        Parameters
        ----------
        template_path : str
            The path to the directory containing the templates.

        Returns
        -------
        Dict[str, str]
            A dictionary containing the names and paths of the templates in the directory.
        """

        all_templates = glob.glob(f"{template_path}/*.jinja")
        template_names = [os.path.basename(template) for template in all_templates]
        template_dict = dict(zip(template_names, all_templates))
        return template_dict

    def get_metadata(self, model_name, template_name, template_path):

        """
        Returns the metadata for a given template.
        """

        template_name, _ = template_name.split(".jinja")
        metadata_files = glob(os.path.join(template_path, template_name, "*.json"))
        meta_content = read_json(metadata_files[0])
        for metadata in meta_content:
            if model_name in metadata["models"]:
                metadata["file_path"] = os.path.join(template_path, template_name)
                return metadata

        return None

    def update_default_variable_values(self, new_defaults: Dict[str, Any]) -> None:
        """
        Updates the default variable values with the given dictionary.

        Parameters
        ----------
        new_defaults : Dict[str, Any]
            A dictionary mapping variable names to default values.
        """
        """Updates the default variable values with the given dictionary."""
        self.default_variable_values.update(new_defaults)

    def load_multiple_templates(self, templates: List):
        """
        Loads multiple templates from a list and returns a dictionary containing their information.

        Parameters
        ----------
        templates : List
            A list of paths to the templates.

        Returns
        -------
        dict
            A dictionary containing information on the loaded templates.
        """
        template_dict = {}
        for template in templates:
            uuid_key = str(uuid.uuid4())
            name = os.path.basename(template) + "_" + uuid_key
            template_dict[name] = self.load_template(template)
        return template_dict

    def load_template(self, template: str, from_string: bool = False):
        """
        Loads a single template and returns its information as a dictionary.

        Parameters
        ----------
        template : str
            The path to the template to load or the template content as a string if from_string is True.
        from_string : bool, optional
            Whether the template parameter contains the template content as a string.

        Returns
        -------
        dict
            A dictionary containing information on the loaded template.
        """

        if template in self.loaded_templates:
            return self.loaded_templates[template]

        if from_string:
            template_instance = Template(template)
            template_data = {
                "template_name": "from_string",
                "template_dir": None,
                "environment":  None,
                "template": template_instance,
            }
        else:
            current_dir = os.path.dirname(os.path.realpath(__file__))
            current_dir, _ = os.path.split(current_dir)
            templates_dir = os.path.join(current_dir, "prompts", "text2text")
            all_folders = {
                f"{folder}.jinja": folder for folder in os.listdir(templates_dir)
            }

            if template in all_folders:
                meta_data = self.get_metadata(self.model.model, template, templates_dir)
                template_name = meta_data["file_name"]
                template_dir  = meta_data["file_path"]
                environment   = Environment(loader=FileSystemLoader(template_dir))
                template_instance = environment.get_template(template_name)

            else:
                self.verify_template_path(template)
                custom_template_dir, custom_template_name = os.path.split(template)

                template_name = custom_template_name
                template_dir = custom_template_dir
                environment = Environment(loader=FileSystemLoader(template_dir))
                template_instance = environment.get_template(custom_template_name)

            template_data = {
                "template_name": template_name,
                "template_dir": template_dir,
                "environment": environment,
                "template": template_instance,
            }

        self.loaded_templates[template] = template_data
        return self.loaded_templates[template]

    def verify_template_path(self, templates_path: str):
        if not os.path.isfile(templates_path):
            raise ValueError(f"Templates path {templates_path} does not exist")
    


    def list_templates(self, environment) -> List[str]:
        """
        Returns a list of available templates in an environment.

        Parameters
        ----------
        environment : Environment
            The environment to get the list of templates from.

        Returns
        -------
        List[str]
            A list of available templates.
        """
        return environment.list_templates()

    def get_multiple_template_variables(self, dict_templates: dict):
        """
        Returns a dictionary of template variables for multiple templates.

        Parameters
        ----------
        dict_templates : dict
            A dictionary containing the templates to get the variables for.

        Returns
        -------
        dict
            A dictionary containing the variables for each template.
        """
        results = {}
        for key, value in dict_templates.items():
            results[key] = self.get_template_variables(
                value["environment"], value["template_name"]
            )
        return results

    def get_template_variables(self, environment, template_name) -> List[str]:
        """
        Returns a list of variables used in a template.

        Parameters
        ----------
        environment : Environment
            The environment that the template is loaded into.
        template_name : str
            The name of the template.

        Returns
        -------
        List[str]
            A list of variables used in the template.
        """
        if template_name in self.prompt_variables_map:
            return self.prompt_variables_map[template_name]
        template_source = environment.loader.get_source(environment, template_name)
        parsed_content = environment.parse(template_source)
        undeclared_variables = meta.find_undeclared_variables(parsed_content)
        self.prompt_variables_map[template_name] = undeclared_variables
        return undeclared_variables

    def generate_prompt(self, template, text_input, **kwargs) -> str:
        """
        Generates a prompt based on a template and input variables.

        Parameters
        ----------
        text_input : str
            The input text to use in the prompt.
        **kwargs : dict
            Additional variables to be used in the template.

        Returns
        -------
        str
            The generated prompt string.
        """

        loader = self.load_template(template, kwargs.get("from_string", False))
        kwargs["text_input"] = text_input

        if loader["environment"]:
            variables = self.get_template_variables(
                loader["environment"], loader["template_name"]
            )
            variables_dict = {temp_variable_: kwargs.get(temp_variable_, None) for temp_variable_ in variables}

            variables_missing = [
                variable
                for variable in variables
                if variable not in kwargs
                and variable not in self.allowed_missing_variables
                and variable not in self.default_variable_values
            ]

            if variables_missing:
                raise ValueError(
                    f"Missing required variables in template {', '.join(variables_missing)}"
                )
        else:
          variables_dict = {"data": None}

        kwargs.update(self.default_variable_values)
        prompt = loader["template"].render(**kwargs).strip()
        return prompt, variables_dict

    def raw_fit(self, prompt: str):
        """
        Generates raw model output for a given prompt.

        Parameters
        ----------
        prompt : str
            The prompt to generate output for.

        Returns
        -------
        List[str]
            A list of raw model output strings.
        """
        outputs = [
            self.model.model_output_raw(output)
            for output in self.model.run(prompts=[prompt])
        ]
        return outputs

    def fit(self, template, text_input, **kwargs):
        """
        Generates model output for a given input using a template.

        Parameters
        ----------
        text_input : str
            The input text to use in the prompt.
        **kwargs : dict
            Additional variables to be used in the template.

        Returns
        -------
        List[str]
            A list of model output strings
        """

        prompt, variables_dict = self.generate_prompt(template, text_input, **kwargs)

        if "verbose" in kwargs:
            if kwargs["verbose"]:
                print(prompt)

        if self.cache_prompt and prompt in self.prompt_cache:
            output = self.prompt_cache[prompt]
            return output
        else:
            response = self.model.execute_with_retry(prompts=[prompt])
            outputs = [
                self.model.model_output(
                    output, max_completion_length=self.max_completion_length
                )
                for output in response
            ]
            if self.cache_prompt:
                self.prompt_cache[prompt] = outputs

        message = create_message(template, prompt, outputs[0]['text'], outputs[0]['parsed']['data']['completion'], **variables_dict)
        self.conversation["messages"].append(message)
        write_json(self.full_path, self.conversation, 'history')
        return outputs
