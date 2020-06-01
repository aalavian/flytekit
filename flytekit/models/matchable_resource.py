from flyteidl.admin import matchable_resource_pb2 as _matchable_resource
from flytekit.models import common as _common


class ClusterResourceAttributes(_common.FlyteIdlEntity):

    def __init__(self, attributes):
        """
        Custom resource attributes which will be applied in cluster resource creation (e.g. quotas).
        Dict keys are the *case-sensitive* names of variables in templatized resource files.
        Dict values should be the custom values which get substituted during resource creation.

        :param dict[Text, Text] attributes: Applied in cluster resource creation (e.g. quotas).
        """
        self._attributes = attributes

    @property
    def attributes(self):
        """
        Custom resource attributes which will be applied in cluster resource management
        :rtype: dict[Text, Text]
        """
        return self._attributes

    def to_flyte_idl(self):
        """
        :rtype: flyteidl.admin.matchable_resource_pb2.ClusterResourceAttributes
        """
        return _matchable_resource.ClusterResourceAttributes(
            attributes=self.attributes,
        )

    @classmethod
    def from_flyte_idl(cls, pb2_object):
        """
        :param flyteidl.admin.matchable_resource_pb2.ClusterResourceAttributes pb2_object:
        :rtype: ClusterResourceAttributes
        """
        return cls(
            attributes=pb2_object.attributes,
        )


class ExecutionQueueAttributes(_common.FlyteIdlEntity):

    def __init__(self, tags):
        """
        Tags used for assigning execution queues for tasks matching a project, domain and optionally, workflow.

        :param list[Text] tags:
        """
        self._tags = tags

    @property
    def tags(self):
        """
        :rtype: list[Text]
        """
        return self._tags

    def to_flyte_idl(self):
        """
        :rtype: flyteidl.admin.matchable_resource_pb2.ExecutionQueueAttributes
        """
        return _matchable_resource.ExecutionQueueAttributes(
            tags=self.tags,
        )

    @classmethod
    def from_flyte_idl(cls, pb2_object):
        """
        :param flyteidl.admin.matchable_resource_pb2.ExecutionQueueAttributes pb2_object:
        :rtype: ExecutionQueueAttributes
        """
        return cls(
            tags=pb2_object.tags,
        )


class MatchingAttributes(_common.FlyteIdlEntity):
    def __init__(self, cluster_resource_attributes=None, execution_queue_attributes=None):
        """
        At most one target from cluster_resource_attributes or execution_queue_attributes can be set.
        :param ClusterResourceAttributes cluster_resource_attributes:
        :param ExecutionQueueAttributes execution_queue_attributes:
        """
        if cluster_resource_attributes and execution_queue_attributes:
            raise ValueError("Only one of cluster_resource_attributes or execution_queue_attributes can be set")
        self._cluster_resource_attributes = cluster_resource_attributes
        self._execution_queue_attributes = execution_queue_attributes

    @property
    def cluster_resource_attributes(self):
        """
        Custom resource attributes which will be applied in cluster resource creation (e.g. quotas).
        :rtype: ClusterResourceAttributes
        """
        return self._cluster_resource_attributes

    @property
    def execution_queue_attributes(self):
        """
        Tags used for assigning execution queues for tasks.
        :rtype: ExecutionQueueAttributes
        """
        return self._execution_queue_attributes

    def to_flyte_idl(self):
        """
        :rtype: flyteidl.admin.matchable_resource_pb2.MatchingAttributes
        """
        return _matchable_resource.MatchingAttributes(
            cluster_resource_attributes=self.cluster_resource_attributes.to_flyte_idl() if
            self.cluster_resource_attributes else None,
            execution_queue_attributes=self.execution_queue_attributes.to_flyte_idl() if self.execution_queue_attributes
            else None,
        )

    @classmethod
    def from_flyte_idl(cls, pb2_object):
        """
        :param flyteidl.admin.matchable_resource_pb2.MatchingAttributes pb2_object:
        :rtype: MatchingAttributes
        """
        return cls(
            cluster_resource_attributes=ClusterResourceAttributes.from_flyte_idl(
                pb2_object.cluster_resource_attributes) if pb2_object.HasField("cluster_resource_attributes") else None,
            execution_queue_attributes=ExecutionQueueAttributes.from_flyte_idl(pb2_object.execution_queue_attributes) if
            pb2_object.HasField("execution_queue_attributes") else None,
        )
