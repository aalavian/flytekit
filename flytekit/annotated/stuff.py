from __future__ import annotations

import inspect
import datetime as _datetime
from typing import List, Dict, Tuple

from flytekit.common import constants as _common_constants
from flytekit.common import interface
from flytekit.common import (
    nodes as _nodes
)
from flytekit.common.exceptions import user as _user_exceptions
from flytekit.common.types import primitives as _primitives
from flytekit.configuration.common import CONFIGURATION_SINGLETON
from flytekit.models import interface as _interface_models, literals as _literal_models
from flytekit.models import task as _task_model, types as _type_models
from flytekit.models.core import workflow as _workflow_model, identifier as _identifier_model
from flytekit.common.promise import Input as _WorkflowInput
from flytekit.common.workflow import Output as _WorkflowOutput
from flytekit.common.types import helpers as _type_helpers

from flytekit import logger

logger.setLevel(10)


# from google
def get_default_args(func):
    signature = inspect.signature(func)
    return {
        k: v.default
        for k, v in signature.parameters.items()
        if v.default is not inspect.Parameter.empty
    }


class SdkNodeWrapper(object):
    def __init__(self, output_name: str, sdk_node: _nodes.SdkNode):
        self._sdk_node = sdk_node
        self._output_name = output_name


class Workflow(object):
    """
    When you assign a name to a node.
    * Any upstream node that is not assigned, recursively assign
    * When you get the call to the constructor, keep in mind there may be duplicate nodes, because they all should
      be wrapper nodes.
    """
    def __init__(self, workflow_function):
        self._workflow_function = workflow_function

    def __call__(self, *args, **kwargs):
        if CONFIGURATION_SINGLETON.x == 1:
            if len(args) > 0:
                raise Exception('not allowed')

            print(f"compilation mode. Args are: {args}")
            print(f"Locals: {locals()}")

            logger.debug(f"Compiling workflow... ")

        else:
            # Can we relax this in the future?  People are used to this right now, so it's okay.
            if len(args) > 0:
                raise Exception('When using the workflow decorator, all inputs must be specified with kwargs only')

            return self._workflow_function(*args, **kwargs)


class WorkflowOutputs(object):
    def __init__(self, *args, **kwargs):
        if len(kwargs) > 0:
            raise Exception("nope, can't do this")
        self._args = args


def workflow(
        _workflow_function=None,
        outputs: List[str]=None
):
    # Unlike for tasks, where we can determine the entire structure of the task by looking at the function's signature,
    # workflows need to have the body of the function itself run at module-load time. This is because the body of the
    # workflow is what expresses the workflow structure.
    def wrapper(fn):
        old_setting = CONFIGURATION_SINGLETON.x
        CONFIGURATION_SINGLETON.x = 1

        task_annotations = fn.__annotations__
        inputs = {k: v for k, v in task_annotations.items() if k != 'return'}

        # Create inputs, just inputs. Outputs need to come later.
        # interface = get_interface_from_task_info(fn.__annotations__, outputs or [])
        # inputs_map = interface.inputs
        inputs_map = get_variable_map(inputs)

        # Create promises out of all the inputs. Check for defaults in the function definition.
        default_inputs = get_default_args(fn)
        input_parameters = []
        for input_name, input_variable_obj in inputs_map.items():
            # _interface_models.Parameter(var=input_variable_obj, default=None, required=required)
            # This is a bit annoying. I'd like to work directly with the Parameter model like above , but for now
            # it's easier to use the promise.Input wrapper
            # This is also annoying... I already have the literal type, but I have to go back to the SDK type (invoking
            # the type engine)... in the constructor, it again turns it back to the literal type when creating the
            # Parameter model.
            sdk_type = _type_helpers.get_sdk_type_from_literal_type(input_variable_obj.type)
            logger.debug(f"Converting literal type {input_variable_obj.type} to sdk type {sdk_type}")
            arg_map = {'default': default_inputs[input_name]} if input_name in default_inputs else {}
            input_parameters.append(_WorkflowInput(name=input_name, type=sdk_type, **arg_map))

        # Fill in call args later - for now this only works for workflows with no inputs
        workflow_outputs = fn()

        # Iterate through the workflow outputs and collect two things
        #  1. Get the outputs and use them to construct the old Output objects
        #      outputs can be like 5, or 'hi'
        #      or promise.NodeOutputs (let's just focus on this one first for POC)
        #      or Input objects from above in the case of a passthrough value.
        #  2. Iterate through the outputs and collect all the nodes.

        # After collecting all the nodes, go through and name all of them.

        # Iterate through nodes returned and assign names.
        # These should line up with the output
        i = 0
        logger.debug(f"Workflow outputs: {outputs}")
        for out in workflow_outputs._args:
            logger.debug(f"Got output wrapper: {out}")
            # import ipdb; ipdb.set_trace()
            # Assume out is an promise.NodeOutput
            # How do you construct common.workflow.Output objects out of promise.NodeOutput objects
            logger.debug(f"Var name {out.var} wf output name {outputs[i]} type: {out.sdk_type.to_flyte_literal_type()}")
            # _WorkflowOutput(out.var, out, interface.ou)
            i += 1

        workflow_instance = Workflow(fn)
        workflow_instance.id = _identifier_model.Identifier(_identifier_model.ResourceType.WORKFLOW, "proj", "dom", "moreblah", "1")

        CONFIGURATION_SINGLETON.x = old_setting
        return workflow_instance

    if _workflow_function:
        return wrapper(_workflow_function)
    else:
        return wrapper


# Has Python in the name because this is the least abstract task. It will have access to the loaded Python function
# itself if run locally, so it will always be a Python task.
# This is analogous to the current SdkRunnableTask. Need to analyze the benefits of duplicating the class versus
# adding to it. Also thinking that the relationship to SdkTask should be a has one relationship rather than an is one.
class PythonTask(object):
    task_type = _common_constants.SdkTaskType.PYTHON_TASK

    def __init__(self, task_function, interface, metadata: _task_model.TaskMetadata, outputs: List[str], info):
        self._task_function = task_function
        self._interface = interface
        self._metadata = metadata
        self._info = info
        self._outputs = outputs

    def __call__(self, *args, **kwargs):
        if CONFIGURATION_SINGLETON.x == 1:
            # Instead of calling the function, scan the inputs, if any, construct a node of inputs and outputs
            # But what do you call the output references?  How do you refer to the node name?

            if len(args) > 0:
                raise _user_exceptions.FlyteAssertion(
                    "When adding a task as a node in a workflow, all inputs must be specified with kwargs only.  We "
                    "detected {} positional args.".format(len(args))
                )

            # TODO: Move away from this to use basic model classes instead. Don't like this create_bindings_for_inputs
            #       function.
            bindings, upstream_nodes = self.interface.create_bindings_for_inputs(kwargs)

            # TODO: Return multiple versions of the _same_ node, but with different output names
            # TODO: Make the metadata name the name of the (function), there's no reason not to use it for that.
            # There is no reason to ever assign a random node id (at least in a non-dynamic context), so we leave it
            # empty for now.
            sdk_node = _nodes.SdkNode(
                id=None,
                metadata=_workflow_model.NodeMetadata("", self.metadata.timeout, self.metadata.retries,
                                                      self.metadata.interruptible),
                bindings=sorted(bindings, key=lambda b: b.var),
                upstream_nodes=upstream_nodes,
                sdk_task=self
            )

            from flytekit.common.nodes import OutputParameterMapper

            ppp = OutputParameterMapper(self.interface.outputs, sdk_node)
            # Don't print this, it'll crash cuz upstream node ids are all None

            if len(self._outputs) > 1:
                # Why do we need to do this? Just for proper binding downstream, nothing else.
                # wrapped_nodes = [SdkNodeWrapper(output_name=self._outputs[i], sdk_node=sdk_node)
                #                  for i in range(0, len(self._outputs))]
                wrapped_nodes = [ppp[self._outputs[i]] for i in range(0, len(self._outputs))]
                return tuple(wrapped_nodes)
            else:
                # return SdkNodeWrapper(output_name=self._outputs[0], sdk_node=sdk_node)
                return ppp[self._outputs[0]]

        else:
            return self._task_function(*args, **kwargs)

    @property
    def interface(self) -> interface.TypedInterface:
        return self._interface

    @property
    def metadata(self) -> _task_model.TaskMetadata:
        return self._metadata


def task(
        _task_function=None,
        outputs: List[str]=None,
        cache_version='',
        retries=0,
        interruptible=None,
        deprecated='',
        storage_request=None,
        cpu_request=None,
        gpu_request=None,
        memory_request=None,
        storage_limit=None,
        cpu_limit=None,
        gpu_limit=None,
        memory_limit=None,
        cache=False,
        timeout=None,
        environment=None,
):
    def wrapper(fn):
        # Just saving everything as a hash for now, will figure out what to do with this in the future.
        task_obj = {}
        task_obj['task_type'] = _common_constants.SdkTaskType.PYTHON_TASK,
        task_obj['retries'] = retries,
        task_obj['storage_request'] = storage_request,
        task_obj['cpu_request'] = cpu_request,
        task_obj['gpu_request'] = gpu_request,
        task_obj['memory_request'] = memory_request,
        task_obj['storage_limit'] = storage_limit,
        task_obj['cpu_limit'] = cpu_limit,
        task_obj['gpu_limit'] = gpu_limit,
        task_obj['memory_limit'] = memory_limit,
        task_obj['environment'] = environment,
        task_obj['custom'] = {}

        metadata = _task_model.TaskMetadata(
            cache,
            _task_model.RuntimeMetadata(
                _task_model.RuntimeMetadata.RuntimeType.FLYTE_SDK,
                '1.2.3',
                'python'
            ),
            timeout or _datetime.timedelta(seconds=0),
            _literal_models.RetryStrategy(retries),
            interruptible,
            cache_version,
            deprecated
        )

        interface = get_interface_from_task_info(fn.__annotations__, outputs or [])

        task_instance = PythonTask(fn, interface, metadata, outputs, task_obj)
        # TODO: One of the things I want to make sure to do is better naming support. At this point, we should already
        #       be able to determine the name of the task right? Can anyone think of situations where we can't?
        #       Where does the current instance tracker come into play?
        task_instance.id = _identifier_model.Identifier(_identifier_model.ResourceType.TASK, "proj", "dom", "blah", "1")

        return task_instance

    if _task_function:
        return wrapper(_task_function)
    else:
        return wrapper


def get_interface_from_task_info(task_annotations: Dict[str, type], output_names: List[str]) -> interface.TypedInterface:
    """
    From the annotations on a task function that the user should have provided, and the output names they want to use
    for each output parameter, construct the TypedInterface object

    For now the fancy object, maybe in the future a dumb object.

    :param task_annotations:
    :param output_names:
    """

    if 'return' not in task_annotations and len(output_names) != 0:
        raise Exception('1fkdsa39mlsda')

    return_types: Tuple[type] = []

    if type(task_annotations['return']) != tuple:
        # If there's just one return value, the return type is not a tuple so let's make it a tuple
        return_types = (task_annotations['return'],)
    else:
        return_types = task_annotations['return']

    if len(output_names) != len(return_types):
        raise Exception(f"Output length mismatch expected {output_names} got {return_types}")

    inputs = {k: v for k, v in task_annotations.items() if k != 'return'}

    inputs_map = get_variable_map(inputs)
    outputs_map = get_variable_map_from_lists(output_names, return_types)
    print(f"Inputs map is {inputs_map}")
    print(f"Outputs map is {outputs_map}")
    interface_model = _interface_models.TypedInterface(inputs_map, outputs_map)

    # Maybe in the future we can just use the model
    return interface.TypedInterface.promote_from_model(interface_model)


def get_variable_map_from_lists(variable_names: List[str], python_types: Tuple[type]) -> Dict[str, _interface_models.Variable]:
    return get_variable_map(dict(zip(variable_names, python_types)))


# One of the things I want to revisit is the concept of SdkTypes. It's an intermediate layer between the IDL types and
# Python types. I feel like things will be simpler if we just get rid of it. I don't really understand why it's
# necessary.
SIMPLE_TYPE_LOOKUP_TABLE: Dict[type, _type_models.LiteralType] = {
    int: _primitives.Integer.to_flyte_literal_type(),
    float: _primitives.Float.to_flyte_literal_type(),
    bool: _primitives.Boolean,
    _datetime.datetime: _primitives.Datetime.to_flyte_literal_type(),
    _datetime.timedelta: _primitives.Timedelta.to_flyte_literal_type(),
    str: _primitives.String.to_flyte_literal_type(),
    dict: _primitives.Generic.to_flyte_literal_type(),
}


def get_variable_map(variable_map: Dict[str, type]) -> Dict[str, _interface_models.Variable]:
    res = {}
    for k, v in variable_map.items():
        if v not in SIMPLE_TYPE_LOOKUP_TABLE:
            raise Exception(f"Python type {v} not yet supported.")
        flyte_literal_type = SIMPLE_TYPE_LOOKUP_TABLE[v]
        res[k] = _interface_models.Variable(type=flyte_literal_type, description=k)

    return res
