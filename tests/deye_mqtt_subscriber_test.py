import pytest

from deye_modbus import DeyeModbus
from deye_mqtt import DeyeMqttClient
from deye_config import DeyeConfig, DeyeMqttConfig

from deye_mqtt_subscriber import DeyeMqttSubscriber
from deye_command_handlers import DeyeCommandHandler


class TestDeyeMqttSubscriber:
    @staticmethod
    @pytest.fixture
    def modbus_mock(mocker) -> DeyeModbus:
        return mocker.Mock(spec=DeyeModbus)

    @staticmethod
    @pytest.fixture
    def mqtt_client_mock(mocker) -> DeyeMqttClient:
        return mocker.Mock(spec=DeyeMqttClient)

    @staticmethod
    @pytest.fixture
    def mqtt_config_mock(mocker) -> DeyeMqttConfig:
        return mocker.Mock(spec=DeyeMqttConfig)

    @staticmethod
    @pytest.fixture
    def config_mock(mocker, mqtt_config_mock) -> DeyeConfig:
        mock = mocker.Mock(spec=DeyeConfig)
        mock.mqtt = mqtt_config_mock
        return mock

    @staticmethod
    @pytest.fixture
    def command_handler_1_mock(mocker) -> DeyeCommandHandler:
        mock = mocker.Mock(spec=DeyeCommandHandler)
        mock.id = "handler1"
        return mock

    @staticmethod
    @pytest.fixture
    def command_handler_2_mock(mocker) -> DeyeCommandHandler:
        mock = mocker.Mock(spec=DeyeCommandHandler)
        mock.id = "handler2"
        return mock

    def test_initialize_active_command_handlers(
        self, config_mock, mqtt_client_mock, modbus_mock, command_handler_1_mock, command_handler_2_mock
    ):
        # given
        config_mock.active_command_handlers = ["handler1"]

        # when
        sut = DeyeMqttSubscriber(
            config_mock,
            mqtt_client_mock,
            modbus_mock,
            [
                command_handler_1_mock,
                command_handler_2_mock,
            ],
        )

        # then
        assert command_handler_1_mock.initialize.called
        assert not command_handler_2_mock.initialize.called

        # and
        assert mqtt_client_mock.connect.called

    def test_no_mqtt_connection_when_no_active_command_handlers(
        self, config_mock, mqtt_client_mock, modbus_mock, command_handler_1_mock, command_handler_2_mock
    ):
        # given
        config_mock.active_command_handlers = []

        # when
        sut = DeyeMqttSubscriber(
            config_mock,
            mqtt_client_mock,
            modbus_mock,
            [
                command_handler_1_mock,
                command_handler_2_mock,
            ],
        )

        # then
        assert not command_handler_1_mock.initialize.called
        assert not command_handler_2_mock.initialize.called

        # and
        assert not mqtt_client_mock.connect.called
