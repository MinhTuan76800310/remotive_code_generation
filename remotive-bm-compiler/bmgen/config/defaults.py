"""Default configuration values for the compiler."""

# Default Remotive Behavioral Model imports
REMOTIVE_IMPORTS = {
    "broker": "from remotivelabs.broker import BrokerClient, Frame",
    "behavioral_model": "from remotivelabs.topology.behavioral_model import BehavioralModel",
    "cli_args": "from remotivelabs.topology.cli.behavioral_model import BehavioralModelArgs",
    "filters": "from remotivelabs.topology.namespaces import filters",
    "can_namespace": "from remotivelabs.topology.namespaces.can import CanNamespace, RestbusConfig",
}

# Default namespace type mappings
NAMESPACE_TYPE_MAP = {
    "can": "CanNamespace",
    "lin": "LinNamespace",  # Future
    "someip": "SomeIPNamespace",  # Future
}

# Default namespace role patterns
INPUT_ONLY_NAMESPACE_TEMPLATE = "{ns_var} = CanNamespace(\"{ns_name}\", broker_client)"
OUTPUT_NAMESPACE_TEMPLATE = "{ns_var} = CanNamespace(\"{ns_name}\", broker_client, restbus_configs=[RestbusConfig([filters.SenderFilter(ecu_name=\"{ecu_name}\")], delay_multiplier=avp.delay_multiplier)])"
