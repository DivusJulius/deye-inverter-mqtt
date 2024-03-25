# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import datetime
import logging
import signal
import threading
import time

from deye_config import DeyeConfig
from deye_connector_factory import DeyeConnectorFactory
from deye_events import DeyeEventList, DeyeLoggerStatusEvent, DeyeObservationEvent
from deye_modbus import DeyeModbus
from deye_mqtt import DeyeMqttClient
from deye_observation import Observation
from deye_sensor import SensorRegisterRanges
from deye_sensors import sensor_list, sensor_register_ranges
from deye_processor_factory import DeyeProcessorFactory


class DeyeDaemon:
    def __init__(self, config: DeyeConfig):
        self.__log = logging.getLogger(DeyeDaemon.__name__)
        self.__config = config
        self.__log.info(
            "Please help me build the list of compatible inverters. "
            "https://github.com/kbialek/deye-inverter-mqtt/issues/41"
        )

        connector = DeyeConnectorFactory(config).create_connector()
        self.modbus = DeyeModbus(connector)
        self.sensors = [s for s in sensor_list if s.in_any_group(self.__config.metric_groups)]
        reg_ranges = [r for r in sensor_register_ranges if r.in_any_group(self.__config.metric_groups)]
        self.reg_ranges = SensorRegisterRanges(
            reg_ranges, max_range_length=config.logger.max_register_range_length
        ).ranges

        mqtt_client = DeyeMqttClient(self.__config)

        self.processors = DeyeProcessorFactory(self.__config, mqtt_client).create_processors(self.modbus, self.sensors)

        self.__last_observations = DeyeEventList()
        self.__event_updated = time.time()

    def do_task(self):
        self.__log.info("Reading start")
        regs = {}
        for reg_range in self.reg_ranges:
            self.__log.info(f"Reading registers [{reg_range}]")
            regs |= self.modbus.read_registers(reg_range.first_reg_address, reg_range.last_reg_address)
        events = DeyeEventList()
        events.append(DeyeLoggerStatusEvent(len(regs) > 0))
        events += self.__get_observations_from_reg_values(regs)
        if not self.__config.publish_on_change or self.__is_device_observation_changed(events):
            for processor in self.processors:
                processor.process(events)
        else:
            self.__log.info("No changes found in received data, or the logger is offline, skipping")
        self.__log.info("Reading completed")

    def __get_observations_from_reg_values(self, regs: dict[int, bytearray]) -> list[DeyeObservationEvent]:
        timestamp = datetime.datetime.now()
        events = []
        for sensor in self.sensors:
            value = sensor.read_value(regs)
            if value is not None:
                observation = Observation(sensor, timestamp, value)
                events.append(DeyeObservationEvent(observation))
                self.__log.debug(f"{observation.sensor.name}: {observation.value_as_str()}")
        return events

    def __is_device_observation_changed(self, events: DeyeEventList) -> bool:
        """Check if the received event observations have changed compared to last published

        Parameters
        ----------
        events : list[DeyeEvent]
            Received event list

        Returns
        -------
        bool
            True if received observation events are different from last published ones
        """
        if events.is_offline():
            self.__log.debug("No observation events received (offline)")
            return False
        if events.compare_observation_events(self.__last_observations):
            self.__log.debug("Event data is unchanged")
            if self.__event_updated + self.__config.event_expiry > time.time():
                self.__log.debug("Event data hasn't expired")
                return False
            else:
                self.__log.info("Event data has expired")
        self.__log.debug("Time since previous update: %s", time.time() - self.__event_updated)
        self.__log.debug("New event data: %s", [str(e) for e in events])
        self.__event_updated = time.time()
        self.__last_observations = events
        return True


class IntervalRunner:
    def __init__(self, interval, action):
        self.__log = logging.getLogger(DeyeDaemon.__name__)
        self.interval = interval
        self.action = action
        self.stopEvent = threading.Event()
        thread = threading.Thread(target=self.__handler)
        self.__log.debug("Start to execute the daemon at intervals of %s seconds", self.interval)
        thread.start()

    def __handler(self):
        self.__invoke_action()
        nextTime = time.time() + self.interval
        while not self.stopEvent.wait(nextTime - time.time()):
            nextTime += self.interval
            self.__invoke_action()

    def __invoke_action(self):
        try:
            self.action()
        except Exception:
            self.__log.exception("Unexpected error during daemon execution")

    def cancel(self, _signum, _frame):
        self.stopEvent.set()


def main():
    config = DeyeConfig.from_env()
    daemon = DeyeDaemon(config)
    time_loop = IntervalRunner(config.data_read_inverval, daemon.do_task)
    signal.signal(signal.SIGINT, time_loop.cancel)
    signal.signal(signal.SIGTERM, time_loop.cancel)


if __name__ == "__main__":
    main()
