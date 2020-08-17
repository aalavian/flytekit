import datetime as _datetime
import uuid as _uuid

from flytekit.common import constants as _constants
from flytekit.common import interface as _interface
from flytekit.common import nodes as _nodes
from flytekit.common import sdk_bases as _sdk_bases
from flytekit.common.core import identifier as _identifier
from flytekit.common.exceptions import scopes as _exception_scopes
from flytekit.common.exceptions import system as _system_exceptions
from flytekit.common.exceptions import user as _user_exceptions
from flytekit.common.mixins import hash as _hash_mixin
from flytekit.common.mixins import registerable as _registerable
from flytekit.configuration import internal as _internal_config
from flytekit.configuration import platform as _platform_config
from flytekit.engines.flyte import engine as _flyte_engine
from flytekit.models import literals as _literal_models
from flytekit.models.admin import workflow as _admin_workflow_model
from flytekit.models.core import identifier as _identifier_model
from flytekit.models.core import workflow as _workflow_models


class SdkWorkflow(
    _hash_mixin.HashOnReferenceMixin,
    _workflow_models.WorkflowTemplate,
    _registerable.RegisterableEntity,
    metaclass=_sdk_bases.ExtendedSdkType,
):
    """
    Previously this class represented both local and control plane constructs. As of this writing, we are making this
    class only a control plane class. Workflow constructs that rely on local code being present have been moved to
    the new PythonWorkflow class.
    """

    def __init__(
        self, nodes, interface, output_bindings, id=None, metadata=None, metadata_defaults=None,
    ):
        """
        :param list[flytekit.common.nodes.SdkNode] nodes:
        :param flytekit.models.interface.TypedInterface interface: Defines a strongly typed interface for the
            Workflow (inputs, outputs).  This can include some optional parameters.
        :param list[flytekit.models.literals.Binding] output_bindings: A list of output bindings that specify how to construct
            workflow outputs. Bindings can pull node outputs or specify literals. All workflow outputs specified in
            the interface field must be bound
            in order for the workflow to be validated. A workflow has an implicit dependency on all of its nodes
            to execute successfully in order to bind final outputs.
        :param flytekit.models.core.identifier.Identifier id: This is an autogenerated id by the system. The id is
            globally unique across Flyte.
        :param WorkflowMetadata metadata: This contains information on how to run the workflow.
        :param flytekit.models.core.workflow.WorkflowMetadataDefaults metadata_defaults: Defaults to be passed
            to nodes contained within workflow.
        """
        for n in nodes:
            for upstream in n.upstream_nodes:
                if upstream.id is None:
                    raise _user_exceptions.FlyteAssertion(
                        "Some nodes contained in the workflow were not found in the workflow description.  Please "
                        "ensure all nodes are either assigned to attributes within the class or an element in a "
                        "list, dict, or tuple which is stored as an attribute in the class."
                    )

        # Allow overrides if specified for all the arguments to the parent class constructor
        id = (
            id
            if id is not None
            else _identifier.Identifier(
                _identifier_model.ResourceType.WORKFLOW,
                _internal_config.PROJECT.get(),
                _internal_config.DOMAIN.get(),
                _uuid.uuid4().hex,
                _internal_config.VERSION.get(),
            )
        )
        metadata = metadata if metadata is not None else _workflow_models.WorkflowMetadata()
        metadata_defaults = (
            metadata_defaults if metadata_defaults is not None else _workflow_models.WorkflowMetadataDefaults()
        )

        super(SdkWorkflow, self).__init__(
            id=id,
            metadata=metadata,
            metadata_defaults=metadata_defaults,
            interface=interface,
            nodes=nodes,
            outputs=output_bindings,
        )

    @property
    def interface(self):
        """
        :rtype: flytekit.common.interface.TypedInterface
        """
        return super(SdkWorkflow, self).interface

    @property
    def entity_type_text(self):
        """
        :rtype: Text
        """
        return "Workflow"

    @property
    def resource_type(self):
        """
        Integer from _identifier.ResourceType enum
        :rtype: int
        """
        return _identifier_model.ResourceType.WORKFLOW

    def get_sub_workflows(self):
        """
        Recursive call that returns all subworkflows in the current workflow

        :rtype: list[SdkWorkflow]
        """
        result = []
        for n in self.nodes:
            if n.workflow_node is not None and n.workflow_node.sub_workflow_ref is not None:
                if n.executable_sdk_object is not None and n.executable_sdk_object.entity_type_text == "Workflow":
                    result.append(n.executable_sdk_object)
                    result.extend(n.executable_sdk_object.get_sub_workflows())
                else:
                    raise _system_exceptions.FlyteSystemException(
                        "workflow node with subworkflow found but bad executable "
                        "object {}".format(n.executable_sdk_object)
                    )
            # Ignore other node types (branch, task)

        return result

    @classmethod
    @_exception_scopes.system_entry_point
    def fetch(cls, project, domain, name, version=None):
        """
        This function uses the engine loader to call create a hydrated task from Admin.
        :param Text project:
        :param Text domain:
        :param Text name:
        :param Text version:
        :rtype: SdkWorkflow
        """
        version = version or _internal_config.VERSION.get()
        workflow_id = _identifier.Identifier(_identifier_model.ResourceType.WORKFLOW, project, domain, name, version)
        admin_workflow = _flyte_engine._FlyteClientManager(
            _platform_config.URL.get(), insecure=_platform_config.INSECURE.get()
        ).client.get_workflow(workflow_id)
        cwc = admin_workflow.closure.compiled_workflow
        primary_template = cwc.primary.template
        sub_workflow_map = {sw.template.id: sw.template for sw in cwc.sub_workflows}
        task_map = {t.template.id: t.template for t in cwc.tasks}
        sdk_workflow = cls.promote_from_model(primary_template, sub_workflow_map, task_map)
        sdk_workflow._id = workflow_id
        return sdk_workflow

    @classmethod
    def get_non_system_nodes(cls, nodes):
        """
        :param list[flytekit.models.core.workflow.Node] nodes:
        :rtype: list[flytekit.models.core.workflow.Node]
        """
        return [n for n in nodes if n.id not in {_constants.START_NODE_ID, _constants.END_NODE_ID}]

    @classmethod
    def promote_from_model(cls, base_model, sub_workflows=None, tasks=None):
        """
        :param flytekit.models.core.workflow.WorkflowTemplate base_model:
        :param dict[flytekit.models.core.identifier.Identifier, flytekit.models.core.workflow.WorkflowTemplate]
            sub_workflows: Provide a list of WorkflowTemplate
            models (should be returned from Admin as part of the admin CompiledWorkflowClosure. Relevant sub-workflows
            should always be provided.
        :param dict[flytekit.models.core.identifier.Identifier, flytekit.models.task.TaskTemplate] tasks: Same as above
            but for tasks. If tasks are not provided relevant TaskTemplates will be fetched from Admin
        :rtype: SdkWorkflow
        """
        base_model_non_system_nodes = cls.get_non_system_nodes(base_model.nodes)
        sub_workflows = sub_workflows or {}
        tasks = tasks or {}
        node_map = {
            n.id: _nodes.SdkNode.promote_from_model(n, sub_workflows, tasks) for n in base_model_non_system_nodes
        }

        # Set upstream nodes for each node
        for n in base_model_non_system_nodes:
            current = node_map[n.id]
            for upstream_id in current.upstream_node_ids:
                upstream_node = node_map[upstream_id]
                current << upstream_node

        # No inputs/outputs specified, see the constructor for more information on the overrides.
        return cls(
            nodes=list(node_map.values()),
            id=_identifier.Identifier.promote_from_model(base_model.id),
            metadata=base_model.metadata,
            metadata_defaults=base_model.metadata_defaults,
            interface=_interface.TypedInterface.promote_from_model(base_model.interface),
            output_bindings=base_model.outputs,
        )

    @_exception_scopes.system_entry_point
    def register(self, project, domain, name, version):
        """
        :param Text project:
        :param Text domain:
        :param Text name:
        :param Text version:
        """
        self.validate()
        id_to_register = _identifier.Identifier(_identifier_model.ResourceType.WORKFLOW, project, domain, name, version)
        old_id = self.id
        self._id = id_to_register
        try:
            client = _flyte_engine._FlyteClientManager(
                _platform_config.URL.get(), insecure=_platform_config.INSECURE.get()
            ).client
            sub_workflows = self.get_sub_workflows()
            client.create_workflow(id_to_register, _admin_workflow_model.WorkflowSpec(self, sub_workflows,))
            self._id = id_to_register
            return str(id_to_register)
        except _user_exceptions.FlyteEntityAlreadyExistsException:
            pass
        except Exception:
            self._id = old_id
            raise

    @_exception_scopes.system_entry_point
    def serialize(self):
        """
        Serializing a workflow should produce an object similar to what the registration step produces, in preparation
        for actual registration to Admin.

        :rtype: flyteidl.admin.workflow_pb2.WorkflowSpec
        """
        sub_workflows = self.get_sub_workflows()
        return _admin_workflow_model.WorkflowSpec(self, sub_workflows,).to_flyte_idl()

    @_exception_scopes.system_entry_point
    def validate(self):
        pass

    @_exception_scopes.system_entry_point
    def create_launch_plan(self, *args, **kwargs):
        raise Exception("This can't be done right now.")

    @_exception_scopes.system_entry_point
    def __call__(self, *args, **input_map):
        if len(args) > 0:
            raise _user_exceptions.FlyteAssertion(
                "When adding a workflow as a node in a workflow, all inputs must be specified with kwargs only.  We "
                "detected {} positional args.".format(len(args))
            )

        bindings, upstream_nodes = self.interface.create_bindings_for_inputs(input_map)

        node = _nodes.SdkNode(
            id=None,
            metadata=_workflow_models.NodeMetadata(
                "placeholder", _datetime.timedelta(), _literal_models.RetryStrategy(0)
            ),
            upstream_nodes=upstream_nodes,
            bindings=sorted(bindings, key=lambda b: b.var),
            sdk_workflow=self,
        )
        return node
