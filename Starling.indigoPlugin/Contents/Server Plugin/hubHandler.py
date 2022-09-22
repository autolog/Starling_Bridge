#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Starling - Hub Handler © Autolog 2022
#

try:
    # noinspection PyUnresolvedReferences
    import indigo
    import requests
except ImportError:
    pass

import queue
import sys
import threading
import time
import traceback

from constants import *  # Also imports logging


def _no_image():
    try:
        return getattr(indigo.kStateImageSel, "NoImage")  # For Python 3
    except AttributeError:
        return getattr(indigo.kStateImageSel, "N/A")


# noinspection PyPep8Naming
class Thread_Hub_Handler(threading.Thread):

    # This class handles Starling Hub processing

    def __init__(self, plugin_globals, starling_hub_device_id, event):
        try:

            threading.Thread.__init__(self)

            self.globals = plugin_globals

            self.starling_hub_device_id = starling_hub_device_id

            self.hubHandlerLogger = logging.getLogger("Plugin.HUB_HANDLER")

            self.threadStop = event

            self.requests_prefix = None
            self.requests_suffix = None

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def exception_handler(self, exception_error_message, log_failing_statement):
        filename, line_number, method, statement = traceback.extract_tb(sys.exc_info()[2])[-1]  # noqa [Ignore duplicate code warning]
        module = filename.split('/')
        log_message = u"'{0}' in module '{1}', method '{2}'".format(exception_error_message, module[-1], method)
        if log_failing_statement:
            log_message = log_message + u"\n   Failing statement [line {0}]: '{1}'".format(line_number, statement)
        else:
            log_message = log_message + u" at line {0}".format(line_number)
        self.hubHandlerLogger.error(log_message)

    def run(self):
        try:
            time.sleep(2)
            while not self.threadStop.is_set():
                try:
                    priority, command, nest_device_list, argument_list = self.globals[QUEUES][self.starling_hub_device_id].get(True, 5)
                    # self.hubHandlerLogger.warning(f"Queue [Debug={self.debug_nest_protect_count}]: Priority={priority}, Command={command}, Nest Device List={nest_device_list}")

                    if command == API_COMMAND_STATUS:
                        self.handle_status_command()
                    elif command in [API_COMMAND_POLL_DEVICE, API_COMMAND_START_DEVICE]:
                        for nest_dev_id in nest_device_list:
                            self.handle_devices_command(command, nest_dev_id)
                    elif command in [SET_TARGET_TEMPERATURE, SET_TARGET_COOLING_THRESHOLD_TEMPERATURE, SET_TARGET_HEATING_THRESHOLD_TEMPERATURE]:
                        nest_dev_id = nest_device_list[0]
                        target_temperature = argument_list[0]
                        state_key = argument_list[1]
                        log_action_name = argument_list[2]
                        self.set_thermostat_temperature(command, nest_dev_id, target_temperature, state_key, log_action_name)
                    elif command == SET_HVAC_MODE:
                        nest_dev_id = nest_device_list[0]
                        hvac_mode_translated = argument_list[0]
                        new_indigo_hvac_mode = argument_list[1]
                        self.set_hvac_mode(nest_dev_id, hvac_mode_translated, new_indigo_hvac_mode)
                    elif command == SET_ECO_MODE:
                        nest_dev_id = nest_device_list[0]
                        eco_mode = argument_list[0]  # Bool: True | False
                        eco_mode_ui = argument_list[1]
                        self.set_eco_mode(nest_dev_id, eco_mode, eco_mode_ui)
                    elif command == SET_FAN:
                        nest_dev_id = nest_device_list[0]
                        fan_running = argument_list[0]  # Bool: True | False
                        fan_running_ui = argument_list[1]
                        self.set_fan_running(nest_dev_id, fan_running, fan_running_ui)
                    elif command == SET_HOT_WATER:
                        nest_dev_id = nest_device_list[0]
                        hot_water_enabled = argument_list[0]  # Bool: True | False
                        hot_water_ui = argument_list[1]
                        self.set_hot_water(nest_dev_id, hot_water_enabled, hot_water_ui)
                    elif command == SET_HUMIDIFIER:
                        nest_dev_id = nest_device_list[0]
                        humidifier_active = argument_list[0]  # Bool: True | False
                        humidifier_ui = argument_list[1]
                        self.set_humidifier(nest_dev_id, humidifier_active, humidifier_ui)
                    elif command == SET_HUMIDIFIER_LEVEL:
                        nest_dev_id = nest_device_list[0]
                        humidifier_target_level = argument_list[0]  # int (0 - 100)
                        humidifier_ui = argument_list[1]
                        self.set_humidifier_level(nest_dev_id, humidifier_target_level, humidifier_ui)
                    elif command == SET_HOME_AWAY:
                        nest_dev_id = nest_device_list[0]
                        humidifier_active = argument_list[0]  # Bool: True | False
                        self.set_home_away(nest_dev_id, humidifier_active)

                    if command == STOP_THREAD:
                        break

                except queue.Empty:
                    pass
                    # self.hubHandlerLogger.warning(f"Queue: EMPTY")
                except Exception as exception_error:
                    self.exception_handler(exception_error, True)  # Log error and display failing statement
                    break

            self.hubHandlerLogger.debug("Hub Handler Thread close-down commencing.")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def handle_status_command(self):
        try:
            dev = indigo.devices[self.starling_hub_device_id]

            status, result = self.access_starling_hub(dev, GET_CONTROL_API_STATUS, "status")

            if status == "OK":
                self.globals[HUBS][dev.id][STARLING_API_VERSION] = float(result["apiVersion"])
                api_version = f"API: {self.globals[HUBS][dev.id][STARLING_API_VERSION]}"
                props = dev.pluginProps
                if api_version != props.get("version", ""):
                    props["version"] = api_version
                    dev.replacePluginPropsOnServer(props)

                self.hubHandlerLogger.debug(f"Starling API: Status={status}, Result='{result}'")

                keyValueList = [
                    {"key": "api_version", "value": result["apiVersion"]},
                    {"key": "api_ready", "value": result["apiReady"]},
                    {"key": "connected_to_nest", "value": result["connectedToNest"]},
                    {"key": "app_name", "value": result["appName"]},
                    {"key": "permission_read", "value": result["permissions"]["read"]},
                    {"key": "permission_write", "value": result["permissions"]["write"]},
                    {"key": "permission_camera", "value": result["permissions"]["camera"]},
                    {"key": "status", "value": "Connected"},
                    {"key": "status_message", "value": status}
                ]
                dev.updateStatesOnServer(keyValueList)
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
            else:
                error_code = result[0]
                # error_message = result[1]
                keyValueList = [
                    {"key": "api_ready", "value": False},
                    {"key": "connected_to_nest", "value": False},
                    {"key": "status", "value": "Disconnected"},
                    {"key": "status_message", "value": error_code}
                ]
                dev.updateStatesOnServer(keyValueList)
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                return

            # Now detect Nest devices attached to the Starling Hub
            status, result = self.access_starling_hub(dev, GET_CONTROL_API_DEVICES,"devices")

            if status == "OK":
                # All is good

                for nest_device in result["devices"]:
                    # self.hubHandlerLogger.info(f"Nest Device: {nest_device}")
                    nest_type = nest_device["type"]
                    nest_device_id = nest_device["id"]
                    nest_where = nest_device["where"]
                    nest_name = nest_device["name"]
                    nest_serial_number = nest_device["serialNumber"]
                    nest_structure_name = "false"
                    if self.globals[HUBS][dev.id][STARLING_API_VERSION] >= 1.2:
                        nest_structure_name = nest_device["structureName"]
                    nest_supports_streaming = "false"
                    if self.globals[HUBS][dev.id][STARLING_API_VERSION] >= 1.2:
                        nest_supports_streaming = nest_device.get("supportsStreaming", "false")

                    # self.hubHandlerLogger.warning(f"DEBUG: Nest Device: {nest_name} located in '{nest_where}', [{nest_type} | {nest_device_id}]")

                    if nest_device_id not in self.globals[HUBS][dev.id][NEST_DEVICES_BY_NEST_ID]:
                        self.globals[HUBS][dev.id][NEST_DEVICES_BY_NEST_ID][nest_device_id] = dict()
                        self.globals[HUBS][dev.id][NEST_DEVICES_BY_NEST_ID][nest_device_id][INDIGO_DEV_ID] = 0  # No Indigo device created for this Nest device
                        indigo_device_type_id = self.derive_nest_deviceTypeId(nest_type)
                        self.globals[HUBS][dev.id][NEST_DEVICES_BY_NEST_ID][nest_device_id][INDIGO_DEVICE_TYPE_ID] = indigo_device_type_id
                        self.globals[HUBS][dev.id][NEST_DEVICES_BY_NEST_ID][nest_device_id][NEST_NAME] = nest_name
                        self.globals[HUBS][dev.id][NEST_DEVICES_BY_NEST_ID][nest_device_id][NEST_WHERE] = nest_where
                    else:
                        indigo_nest_device_id = self.globals[HUBS][dev.id][NEST_DEVICES_BY_NEST_ID][nest_device_id][INDIGO_DEV_ID]
                        if indigo_nest_device_id != 0:
                            # NEST_NAME & NEST_WHERE will already be setup
                            nest_dev = indigo.devices[indigo_nest_device_id]
                            nest_deviceTypeId = self.derive_nest_deviceTypeId(nest_type)
                            if nest_deviceTypeId != nest_dev.deviceTypeId:
                                self.hubHandlerLogger.warning(f"Indigo Device Type '{nest_dev.deviceTypeId}' for '{nest_dev.name}' inconsistent with derived device type '{nest_deviceTypeId}' from Nest Device Type '{nest_type}'")
                        else:
                            # TODO: Check whether we want the two lines to excute regardless? 30-Mar-22
                            self.globals[HUBS][dev.id][NEST_DEVICES_BY_NEST_ID][nest_device_id][NEST_NAME] = nest_name
                            self.globals[HUBS][dev.id][NEST_DEVICES_BY_NEST_ID][nest_device_id][NEST_WHERE] = nest_where

                # self.hubHandlerLogger.info(f"Device '{dev.name}' Started")
            else:
                error_code = result[0]
                # error_message = result[1]
                keyValueList = [
                    {"key": "api_ready", "value": False},
                    {"key": "connected_to_nest", "value": False},
                    {"key": "status", "value": "Disconnected"},
                    {"key": "status_message", "value": error_code}
                ]
                dev.updateStatesOnServer(keyValueList)
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                return

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def handle_devices_command(self, command, nest_device_id):
        try:
            if self.starling_hub_device_id not in indigo.devices:
                return
            starling_hub_dev = indigo.devices[self.starling_hub_device_id]

            nest_dev = indigo.devices[nest_device_id]
            nest_dev_props = nest_dev.pluginProps
            hub_id = int(nest_dev_props.get("starling_hub_indigo_id", 0))
            if hub_id == 0:
                self.hubHandlerLogger.error(f"Warning: Starling Hub id not defined for {nest_dev.name}")
                return

            nest_device_command = f"devices/{nest_dev.address}"

            status, result = self.access_starling_hub(starling_hub_dev, GET_CONTROL_API_DEVICES_ID, nest_device_command)

            if status != "OK":
                error_code = result[0]
                # error_message = result[1]
                keyValueList = [
                    {"key": "status", "value": "Disconnected"},
                    {"key": "status_message", "value": error_code}
                ]
                nest_dev.updateStatesOnServer(keyValueList)
                nest_dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                starling_hub_dev.updateStatesOnServer(keyValueList)
                starling_hub_dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                return

            else:
                # All is good

                # self.hubHandlerLogger.warning(f"HANDLE_DEVICES_COMMAND: Status={status},\nResult='{result}'")

                if starling_hub_dev.states["status"] != "Connected":
                    keyValueList = list()
                    keyValueList.append({"key": "status", "value": "Connected"})
                    keyValueList.append({"key": "status_message", "value": "Connected"})
                    starling_hub_dev.updateStatesOnServer(keyValueList)

                    message_ui = f"{starling_hub_dev.name} successfully connected"
                    self.hubHandlerLogger.info(message_ui)

                keyValueList = list()
                if nest_dev.states["status"] != "Connected":
                    keyValueList.append({"key": "status", "value": "Connected"})
                    keyValueList.append({"key": "status_message", "value": "Connected"})
                    # keyValueList.append({"key": "onOffState", "value": False, "uiValue": "OK"})

                nest_properties = result["properties"]

                # Properties common across all devices
                nest_type = nest_properties["type"]
                nest_id = nest_properties["id"]
                nest_where = nest_properties["where"]
                nest_name = nest_properties["name"]
                nest_serial_number = nest_properties["serialNumber"]
                nest_structure_name = nest_properties["structureName"]

                # Properties common across all devices
                # keyValueList.append({"key": "type", "value": nest_type})
                # keyValueList.append({"key": "id", "value": nest_id})
                if nest_dev.deviceTypeId != "nestHomeAwayControl":
                    if nest_dev.states["where"] != nest_where:
                        keyValueList.append({"key": "where", "value": nest_where})
                if nest_dev.states["name"] != nest_name:
                    keyValueList.append({"key": "name", "value": nest_name})
                if nest_dev.deviceTypeId != "nestHomeAwayControl":
                    if nest_dev.states["serial_number"] != nest_serial_number:
                        keyValueList.append({"key": "serial_number", "value": nest_serial_number})
                if nest_dev.states["structure_name"] != nest_structure_name:
                    keyValueList.append({"key": "structure_name", "value": nest_structure_name})

                if nest_dev.deviceTypeId == "nestThermostat":
                    self.handle_devices_command_thermostat(command, hub_id, nest_dev, nest_properties, keyValueList)
                elif nest_dev.deviceTypeId == "nestProtect":
                    self.handle_devices_command_protect(command, hub_id, nest_dev, nest_properties, keyValueList)
                elif nest_dev.deviceTypeId == "nestHomeAwayControl":
                    self.handle_devices_command_home_away_control(command, hub_id, nest_dev, nest_properties, keyValueList)
                elif nest_dev.deviceTypeId == "nestWeather":
                    self.handle_devices_command_weather(command, hub_id, nest_dev, nest_properties, keyValueList)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def handle_devices_command_protect(self, command, hub_id, nest_dev, nest_properties, keyValueList):
        try:
            # DEBUG SETUP START ...
            if "_starling_debug" in indigo.variables and indigo.variables["_starling_debug"].getValue(bool):
                starling_debug_protect = indigo.variables["_starling_debug_protect"].getValue(bool)
                if starling_debug_protect:
                    if "Kitchen" in nest_properties["where"]:
                        nest_properties["smokeDetected"] = indigo.variables["starling_smoke_kitchen"].getValue(bool)
                        nest_properties["coDetected"] = indigo.variables["starling_co_kitchen"].getValue(bool)
                    elif "Den" in nest_properties["where"]:
                        nest_properties["smokeDetected"] = indigo.variables["starling_smoke_study"].getValue(bool)
                        nest_properties["coDetected"] = indigo.variables["starling_co_study"].getValue(bool)
                    nest_properties["manualTestActive"] = indigo.variables["starling_manual_test"].getValue(bool)
                    if indigo.variables["starling_occupancy_enabled"].getValue(bool):
                        nest_properties["occupancyDetected"] = indigo.variables["starling_occupancy"].getValue(bool)
                    nest_properties["batteryStatus"] = indigo.variables["starling_battery"].value
            # .. DEBUG SETUP END

            # Properties below already processed by invoking metheod:
            #   nest_id = nest_properties["id"]
            #   nest_name = nest_properties["name"]
            #   nest_serial_number = nest_properties["serialNumber"]
            #   nest_structure_name = nest_properties["structureName"]
            #   nest_type = nest_properties["type"]
            #   nest_where = nest_properties["where"]

            # Nest Protect Specific properties
            nest_battery_status = nest_properties["batteryStatus"]
            nest_co_detected = nest_properties["coDetected"]
            nest_manual_test_active = nest_properties["manualTestActive"]
            nest_occupancy_detected = nest_properties.get("occupancyDetected", None)
            nest_smoke_detected = nest_properties["smokeDetected"]

            # Battery Status Check
            battery_level = 100 if nest_battery_status == "normal" else 20
            if nest_dev.states["batteryLevel"] != battery_level:
                keyValueList.append({"key": "batteryLevel", "value": battery_level})
                keyValueList.append({"key": "batteryStatus", "value": nest_battery_status})

            # CO Device Check
            nest_dev_co_id = self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][CO_DEV_ID]
            if nest_dev_co_id == 0:
                # Create CO device
                nest_dev_co_id = self.create_co_sensor_device(hub_id, nest_dev)
            nest_dev_co = indigo.devices[nest_dev_co_id]
            keyValueList_co = list()

            if (nest_dev_co.states["onOffState"] != nest_co_detected) or (command == API_COMMAND_START_DEVICE):
                keyValueList_co.append({"key": "onOffState", "value": nest_co_detected})
                if not nest_co_detected:
                    if nest_dev_co.states["status"] != "OK":
                        keyValueList_co.append({"key": "status", "value": "OK"})
                    status_message = "No CO detected"
                    if nest_dev_co.states["status_message"] != status_message:
                        keyValueList_co.append({"key": "status_message", "value": status_message})
                else:
                    status = "CO"
                    self.hubHandlerLogger.critical(f"{status} detected by {nest_dev.name}")  # Now replaced by a trigger
                    keyValueList_co.append({"key": "status", "value": status})
                    keyValueList_co.append({"key": "status_message", "value": f"{status} detected!"})

            k_state_image_sel_co = indigo.kStateImageSel.SensorOff
            if nest_co_detected:
                k_state_image_sel_co = indigo.kStateImageSel.SensorTripped

            # if len(keyValueList_co) > 0:
            #     nest_dev_co.updateStatesOnServer(keyValueList_co)
            # if nest_dev_co.displayStateImageSel != k_state_image_sel_co:
            #     nest_dev_co.updateStateImageOnServer(k_state_image_sel_co)

            # Motion [aka Occupancy] Device Check
            nest_dev_motion_id = self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][MOTION_DEV_ID]
            if nest_occupancy_detected is None:
                if nest_dev_motion_id != 0:
                    # Force a restart of the Nest Protect device to update linked devices and remove linked Motion device
                    props = nest_dev.ownerProps
                    props["nest_occupancy_detected_enabled"] = False
                    nest_dev.replacePluginPropsOnServer(props)

                    indigo.device.enable(nest_dev.id, value=False)  # disable
                    indigo.device.enable(nest_dev.id, value=True)  # enable
                    return
            else:
                if nest_dev_motion_id == 0:
                    # Create Motion device
                    nest_dev_motion_id = self.create_motion_sensor_device(hub_id, nest_dev)
                nest_dev_motion = indigo.devices[nest_dev_motion_id]
                keyValueList_motion = list()

                if (nest_dev_motion.states["onOffState"] != nest_occupancy_detected) or (command == API_COMMAND_START_DEVICE):
                    keyValueList_motion.append({"key": "onOffState", "value": nest_occupancy_detected})
                    if not nest_occupancy_detected:
                        if nest_dev_motion.states["status"] != "OK":
                            keyValueList_motion.append({"key": "status", "value": "OK"})
                        status_message = "No motion detected"
                        if nest_dev_motion.states["status_message"] != status_message:
                            keyValueList_motion.append({"key": "status_message", "value": status_message})
                    else:
                        status = "Motion"
                        self.hubHandlerLogger.info(f"{status} detected by {nest_dev.name}")
                        keyValueList_motion.append({"key": "status", "value": status})
                        keyValueList_motion.append({"key": "status_message", "value": f"{status} detected!"})

                k_state_image_sel_motion = indigo.kStateImageSel.MotionSensor
                if nest_occupancy_detected:
                    k_state_image_sel_motion = indigo.kStateImageSel.MotionSensorTripped

                if len(keyValueList_motion) > 0:
                    nest_dev_motion.updateStatesOnServer(keyValueList_motion)
                if nest_dev_motion.displayStateImageSel != k_state_image_sel_motion:
                    nest_dev_motion.updateStateImageOnServer(k_state_image_sel_motion)

            # Manual Test Active
            if (nest_dev.states["manual_test_active"] != nest_manual_test_active) or (command == API_COMMAND_START_DEVICE):
                keyValueList.append({"key": "manual_test_active", "value": nest_manual_test_active})
                if not nest_smoke_detected:
                    # Only update status and status message if no smoke detected
                    if nest_manual_test_active:
                        status = "Manual Test"
                        status_message = f"{status} in progress"
                        if nest_dev.states["status"] != status:
                            keyValueList.append({"key": "status", "value": status})
                        if nest_dev.states["status_message"] != status_message:
                            keyValueList.append({"key": "status_message", "value": status_message})
                    else:
                        if nest_dev.states["status"] != "OK":
                            keyValueList.append({"key": "status", "value": "OK"})
                        status_message = "No Smoke detected"
                        if nest_dev.states["status_message"] != status_message:
                            keyValueList.append({"key": "status_message", "value": status_message})

            # Smoke
            if (nest_dev.states["onOffState"] != nest_smoke_detected) or (command == API_COMMAND_START_DEVICE):
                keyValueList.append({"key": "onOffState", "value": nest_smoke_detected})

                if nest_smoke_detected:
                    status = "Smoke"
                    self.hubHandlerLogger.critical(f"{status} detected by {nest_dev.name}")
                    keyValueList.append({"key": "status", "value": status})
                    keyValueList.append({"key": "status_message", "value": f"{status} detected!"})
                elif nest_manual_test_active:
                    status = "Manual Test"
                    if nest_dev.states["status"] != status:
                        keyValueList.append({"key": "status", "value": status})
                    status_message = f"{status} in progress"
                    if nest_dev.states["status_message"] != status_message:
                        keyValueList.append({"key": "status_message", "value": status_message})
                else:
                    if nest_dev.states["status"] != "OK":
                        keyValueList.append({"key": "status", "value": "OK"})
                    status_message = "No Smoke detected"
                    if nest_dev.states["status_message"] != status_message:
                        keyValueList.append({"key": "status_message", "value": status_message})

            k_state_image_sel = indigo.kStateImageSel.SensorOff
            if nest_manual_test_active:
                k_state_image_sel = indigo.kStateImageSel.SensorOn
            if nest_smoke_detected:
                k_state_image_sel = indigo.kStateImageSel.SensorTripped

            # Alert In Progess + Trigger Check
            nest_smoke_previously_detected = nest_dev.states["onOffState"]
            nest_co_previously_detected = nest_dev_co.states["onOffState"]

            nest_alert_previously_in_progress = nest_smoke_previously_detected | nest_co_previously_detected
            nest_alert_currently_in_progress = nest_smoke_detected | nest_co_detected

            alerts_previously_in_progress = len(self.globals[ALERTS_IN_PROGRESS])

            if (nest_alert_previously_in_progress != nest_alert_currently_in_progress) or (command == API_COMMAND_START_DEVICE):
                if nest_alert_currently_in_progress:
                    self.globals[ALERTS_IN_PROGRESS][nest_dev.id] = True
                else:
                    if nest_dev.id in self.globals[ALERTS_IN_PROGRESS]:
                        del self.globals[ALERTS_IN_PROGRESS][nest_dev.id]
                alerts_currently_in_progress = len(self.globals[ALERTS_IN_PROGRESS])  # Count of alerts in progress (max 1 per Nest Protect)

                #  Check individual Nest Protect device
                if command == API_COMMAND_START_DEVICE:
                    keyValueList.append({"key": "alert_in_progress", "value": nest_alert_currently_in_progress})
                    if nest_alert_currently_in_progress:
                        self.checkIndividualNestTriggers(nest_dev, nest_alert_currently_in_progress)
                elif nest_dev.states["alert_in_progress"] != nest_alert_currently_in_progress:
                    keyValueList.append({"key": "alert_in_progress", "value": nest_alert_currently_in_progress})
                    self.checkIndividualNestTriggers(nest_dev, nest_alert_currently_in_progress)

                # Check all Nest Protect devices
                if alerts_previously_in_progress != alerts_currently_in_progress:
                    if (alerts_previously_in_progress == 0) or (alerts_currently_in_progress == 0):
                        self.checkAllNestsTriggers(alerts_currently_in_progress)

            if len(keyValueList) > 0:
                nest_dev.updateStatesOnServer(keyValueList)
            if nest_dev.displayStateImageSel != k_state_image_sel:
                nest_dev.updateStateImageOnServer(k_state_image_sel)

            if len(keyValueList_co) > 0:
                nest_dev_co.updateStatesOnServer(keyValueList_co)
            if nest_dev_co.displayStateImageSel != k_state_image_sel_co:
                nest_dev_co.updateStateImageOnServer(k_state_image_sel_co)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def checkIndividualNestTriggers(self, dev, alert_in_progress):

        if not dev.enabled:
            return
        for trigger in self.globals[TRIGGERS_NEST_PROTECT].values():
            self.hubHandlerLogger.debug(f"{trigger.name}: Testing Event Trigger")

            # self.hubHandlerLogger.info(f"Trigger: {trigger.name}, Alerts In progress: {len(self.globals[ALERTS_IN_PROGRESS])}:\n{trigger}\n")
            if trigger.pluginTypeId in ("alertDetected", "alertNoLongerDetected"):
                if trigger.pluginProps.get("nestProtectDevice", "") == str(dev.id):
                    self.hubHandlerLogger.debug(f"{trigger.name}: Nest protect '{dev.name}'")
                    if trigger.pluginTypeId == "alertDetected":
                        if alert_in_progress:
                            indigo.trigger.execute(trigger)
                    elif trigger.pluginTypeId == "alertNoLongerDetected":
                        if not alert_in_progress:
                            indigo.trigger.execute(trigger)
            else:
                self.hubHandlerLogger.error(f"{trigger.name}: Ignoring Trigger Type {trigger.pluginTypeId}")

    def checkAllNestsTriggers(self, alerts_currently_in_progress):

        for trigger in self.globals[TRIGGERS_NEST_PROTECTS_ALL].values():
            self.hubHandlerLogger.debug(f"{trigger.name}: Testing Event Trigger")

            # self.hubHandlerLogger.info(f"Trigger: {trigger.name}, Alerts In progress: {len(self.globals[ALERTS_IN_PROGRESS])}:\n{trigger}\n")

            if trigger.pluginTypeId == "alertDetectedAnyProtect":
                if alerts_currently_in_progress > 0:
                    indigo.trigger.execute(trigger)
            elif trigger.pluginTypeId == "alerttNoLongeDetectedAnyProtect":
                if alerts_currently_in_progress == 0:
                    indigo.trigger.execute(trigger)
            else:
                self.hubHandlerLogger.error(f"{trigger.name}: Ignoring Trigger Type {trigger.pluginTypeId}")

    def handle_devices_command_thermostat(self, command, hub_id, nest_dev, nest_properties, keyValueList):
        try:
            # DEBUG SETUP START ...
            if "_starling_debug" in indigo.variables and indigo.variables["_starling_debug"].getValue(bool):
                starling_debug_thermostat = indigo.variables["_starling_debug_thermostat"].getValue(bool)
                if starling_debug_thermostat:
                    if indigo.variables["starling_hvac_mode_enabled"].getValue(bool):
                        nest_properties["hvacMode"] = indigo.variables["starling_hvac_mode"].value
                        nest_properties["hvacState"] = indigo.variables["starling_hvac_state"].value
                    if indigo.variables["starling_hot_water_enabled"].getValue(bool):
                        nest_properties["hotWaterEnabled"] = indigo.variables["starling_hot_water"].getValue(bool)
                    elif indigo.variables["starling_hot_water_disabled"].getValue(bool):
                        if "hotWaterEnabled" in nest_properties:
                            del nest_properties["hotWaterEnabled"]
                    nest_properties["canCool"] = indigo.variables["starling_can_cool"].getValue(bool)
                    if nest_properties["canCool"]:
                        nest_properties["targetCoolingThresholdTemperature"] = indigo.variables["starling_threshold_cooling"].getValue(float)
                        nest_properties["targetHeatingThresholdTemperature"] = indigo.variables["starling_threshold_heating"].getValue(float)
                    if indigo.variables["starling_eco_mode_enabled"].getValue(bool):
                        nest_properties["ecoMode"] = indigo.variables["starling_eco_mode"].getValue(bool)
                    elif indigo.variables["starling_eco_mode_disabled"].getValue(bool):
                        if "ecoMode" in nest_properties:
                            del nest_properties["ecoMode"]
                    if indigo.variables["starling_fan_running_enabled"].getValue(bool):
                        nest_properties["fanRunning"] = indigo.variables["starling_fan_running"].getValue(bool)
                    if indigo.variables["starling_humidifier_enabled"].getValue(bool):
                        nest_properties["currentHumidifierState"] = indigo.variables["starling_humidifier_current_state"].value
                        nest_properties["humidifierActive"] = indigo.variables["starling_humidifier_active"].getValue(bool)
                        nest_properties["targetHumidity"] = indigo.variables["starling_humidifier_target_humidity"].getValue(int)
                    if indigo.variables["starling_backplate_temperature_overide_enabled"].getValue(bool):
                        nest_properties["backplateTemperature"] = indigo.variables["starling_backplate_temperature"].getValue(float)
                        nest_properties["currentTemperature"] = indigo.variables["starling_backplate_temperature"].getValue(float)
                    if indigo.variables["starling_humidity_override_enabled"].getValue(bool):
                        nest_properties["humidityPercent"] = indigo.variables["starling_humidity"].getValue(int)
                        if indigo.variables["starling_humidifier_enabled"].getValue(bool):
                            if nest_properties["targetHumidity"] < nest_properties["humidityPercent"]:
                                nest_properties["currentHumidifierState"] = "dehumidifying"
                            elif nest_properties["targetHumidity"] > nest_properties["humidityPercent"]:
                                nest_properties["currentHumidifierState"] = "humidifying"
                            else:
                                nest_properties["currentHumidifierState"] = "idle"
                    if indigo.variables["starling_temp_hold_mode_enabled"].getValue(bool):
                        nest_properties["tempHoldMode"] = indigo.variables["starling_temp_hold_mode"].getValue(bool)
                    if indigo.variables["starling_preset_selected_enabled"].getValue(bool):
                        nest_properties["presetSelected"] = indigo.variables["starling_preset_selected"].value
                    self.hubHandlerLogger.warning(f"Modified Message: {nest_properties} ")

            # .. DEBUG SETUP END

            # Properties below already processed by invoking metheod:
            #   nest_id = nest_properties["id"]
            #   nest_name = nest_properties["name"]
            #   nest_serial_number = nest_properties["serialNumber"]
            #   nest_structure_name = nest_properties["structureName"]
            #   nest_type = nest_properties["type"]
            #   nest_where = nest_properties["where"]

            # Thermostat specific properties
            nest_backplate_temperature = nest_properties["backplateTemperature"]
            nest_can_cool = nest_properties["canCool"]
            nest_can_heat = nest_properties["canHeat"]
            nest_current_humidifier_state = nest_properties.get("currentHumidifierState", None)
            nest_current_temperature = nest_properties["currentTemperature"]
            nest_display_temperature_units = nest_properties["displayTemperatureUnits"]
            nest_eco_mode = nest_properties.get("ecoMode", None)
            nest_fan_running = nest_properties.get("fanRunning", None)
            nest_hot_water_enabled = nest_properties.get("hotWaterEnabled", None)
            nest_humidifier_active = nest_properties.get("humidifierActive", None)
            nest_humidity_percent = nest_properties["humidityPercent"]
            nest_humidity_percent_ui = f"{nest_humidity_percent}%"
            nest_hvac_mode = nest_properties["hvacMode"]
            nest_hvac_state = nest_properties["hvacState"]
            nest_sensor_selected = nest_properties.get("sensorSelected", None)
            nest_preset_selected = nest_properties.get("presetSelected", None)
            nest_target_cooling_threshold_temperature = nest_properties["targetCoolingThresholdTemperature"]
            nest_target_heating_threshold_temperature = nest_properties["targetHeatingThresholdTemperature"]
            nest_target_humidity = nest_properties.get("targetHumidity", None)
            nest_target_humidity_ui = f"{nest_target_humidity}%"
            nest_target_temperature = nest_properties["targetTemperature"]
            nest_temp_hold_mode = nest_properties.get("tempHoldMode", None)

            nest_dev_props = nest_dev.pluginProps

            if command == API_COMMAND_START_DEVICE:
                # nest_dev_props["device_states_initialised"] = True
                nest_dev_props["cooling_enabled"] = nest_can_cool  # Bool
                nest_dev_props["eco_mode_enabled"] = False if nest_eco_mode is None else True
                nest_dev_props["fan_enabled"] = False if nest_fan_running is None else True
                nest_dev_props["hot_water_enabled"] = False if nest_hot_water_enabled is None else True
                nest_dev_props["humidifier_enabled"] = False if nest_current_humidifier_state is None else True
                nest_dev_props["preset_enabled"] = False if nest_preset_selected is None else True
                nest_dev_props["sensor_enabled"] = False if nest_sensor_selected is None else True
                nest_dev_props["temp_hold_mode_enabled"] = False if nest_temp_hold_mode is None else True
                nest_dev.replacePluginPropsOnServer(nest_dev_props)
                nest_dev_id = nest_dev.id
                nest_dev = indigo.devices[nest_dev_id]  # Refresh Indigo Device to ensure Plugin Props updated in working copy
                nest_dev.stateListOrDisplayStateIdChanged()  # Force State List update via getDeviceStateList method

            nest_dev_props = nest_dev.pluginProps

            # TODO: FINISH CHECKING can cool

            if (nest_dev.states["can_cool"] != nest_can_cool) or (command == API_COMMAND_START_DEVICE):
                keyValueList.append({"key": "can_cool", "value": nest_can_cool})

            supports_cool_setpoint = bool(nest_dev_props.get("SupportsCoolSetpoint", False))
            if nest_can_cool != supports_cool_setpoint:
                nest_dev_props["SupportsCoolSetpoint"] = nest_can_cool
                nest_dev.replacePluginPropsOnServer(nest_dev_props)

            if (nest_dev.states["can_heat"] != nest_can_heat) or (command == API_COMMAND_START_DEVICE):
                keyValueList.append({"key": "can_heat", "value": nest_can_heat})
            if nest_can_heat != nest_dev_props.get("supportsHeatSetpoint", False):
                nest_dev_props["supportsHeatSetpoint"] = nest_can_heat
                nest_dev.replacePluginPropsOnServer(nest_dev_props)

            if nest_eco_mode is not None:
                if (nest_dev.states["eco_mode"] != nest_eco_mode) or (command == API_COMMAND_START_DEVICE):
                    keyValueList.append({"key": "eco_mode", "value": nest_eco_mode})
                    if nest_eco_mode:
                        if nest_can_cool:
                            indigo_hvac_mode =indigo.kHvacMode.ProgramHeatCool
                        else:
                            indigo_hvac_mode = indigo.kHvacMode.ProgramHeat
                    else:
                        if nest_can_cool:
                            indigo_hvac_mode = indigo.kHvacMode.HeatCool
                        else:
                            indigo_hvac_mode = indigo.kHvacMode.Heat
                    keyValueList.append({"key": "hvacOperationMode", "value": indigo_hvac_mode})

            if nest_sensor_selected is not None:
                if (nest_dev.states["sensor_selected"] != nest_sensor_selected) or (command == API_COMMAND_START_DEVICE):
                    keyValueList.append({"key": "sensor_selected", "value": nest_sensor_selected})

            if nest_preset_selected is not None:
                if (nest_dev.states["preset_selected"] != nest_preset_selected) or (command == API_COMMAND_START_DEVICE):
                    keyValueList.append({"key": "preset_selected", "value": nest_preset_selected})

            if nest_temp_hold_mode is not None:
                if (nest_dev.states["temperature_hold_mode"] != nest_temp_hold_mode) or (command == API_COMMAND_START_DEVICE):
                    keyValueList.append({"key": "temperature_hold_mode", "value": nest_temp_hold_mode})

            if nest_display_temperature_units == "F":
                nest_backplate_temperature = int(((float(nest_backplate_temperature) * 9) / 5) + 32.0)
                nest_backplate_temperature_ui = f"{nest_backplate_temperature}°F"

                nest_current_temperature = int(((float(nest_current_temperature) * 9) / 5) + 32.0)
                nest_current_temperature_ui = f"{nest_current_temperature}°F"

                if nest_can_cool:
                    nest_target_cooling_threshold_temperature = int(((float(nest_target_cooling_threshold_temperature) * 9) / 5) + 32.0)
                    nest_target_cooling_threshold_temperature_ui = f"{nest_target_cooling_threshold_temperature}°F"

                    nest_target_heating_threshold_temperature = int(((float(nest_target_heating_threshold_temperature) * 9) / 5) + 32.0)
                    nest_target_heating_threshold_temperature_ui = f"{nest_target_heating_threshold_temperature}°F"

                nest_target_temperature = int(((float(nest_target_temperature) * 9) / 5) + 32.0)
                nest_target_temperature_ui = f"{nest_target_temperature}"

            else:
                nest_backplate_temperature = round(nest_backplate_temperature, 1)
                nest_backplate_temperature_ui = f"{nest_backplate_temperature}°C"

                nest_current_temperature = round(nest_current_temperature, 1)
                nest_current_temperature_ui = f"{nest_current_temperature}°C"

                if nest_can_cool:
                    nest_target_cooling_threshold_temperature = round(nest_target_cooling_threshold_temperature, 1)
                    nest_target_cooling_threshold_temperature_ui = f"{nest_target_cooling_threshold_temperature}°C"

                    nest_target_heating_threshold_temperature = round(nest_target_heating_threshold_temperature, 1)
                    nest_target_heating_threshold_temperature_ui = f"{nest_target_heating_threshold_temperature}°C"

                nest_target_temperature = round(nest_target_temperature, 1)
                nest_target_temperature_ui = f"{nest_target_temperature}°C"

            if (nest_dev.states["display_temperature_units"] != nest_display_temperature_units) or (command == API_COMMAND_START_DEVICE):
                keyValueList.append({"key": "display_temperature_units", "value": nest_display_temperature_units})

            if (nest_dev.states["backplate_temperature"] != nest_backplate_temperature) or (command == API_COMMAND_START_DEVICE):
                keyValueList.append({"key": "backplate_temperature", "value": nest_backplate_temperature, "uiValue": nest_backplate_temperature_ui})
            if (nest_dev.states["current_temperature"] != nest_current_temperature) or (command == API_COMMAND_START_DEVICE):
                keyValueList.append({"key": "current_temperature", "value": nest_current_temperature, "uiValue": nest_current_temperature_ui})
                keyValueList.append({"key": "temperatureInput1", "value": nest_current_temperature, "uiValue": nest_current_temperature_ui})
                if not nest_dev_props.get("hideTemperatureBroadcast", False):
                    self.hubHandlerLogger.info(f"Received \"{nest_dev.name}\" temperature update to {nest_current_temperature_ui}")

            hvac_mode_changed = False
            if (nest_dev.states["hvac_mode"] != nest_hvac_mode) or (command == API_COMMAND_START_DEVICE):
                hvac_mode_changed = True
                keyValueList.append({"key": "hvac_mode", "value": nest_hvac_mode})

                # TODO: Enhance following code.

                # Set Indigo required internal state: hvacOperationMode
                if nest_eco_mode is not None and nest_eco_mode:
                    if nest_can_cool:
                        keyValueList.append({"key": "hvacOperationMode", "value": indigo.kHvacMode.ProgramHeatCool})
                    else:
                        keyValueList.append({"key": "hvacOperationMode", "value": indigo.kHvacMode.ProgramHeat})
                    # keyValueList.append({"key": "hvac_mode", "value": "eco"})  # Not a valid Starling Nest Thermostat mode BUT indicates what is happening TODO Remove this?
                else:
                    if nest_hvac_mode == "heat":
                        keyValueList.append({"key": "hvacOperationMode", "value": indigo.kHvacMode.Heat})
                    elif nest_hvac_mode == "cool":
                        keyValueList.append({"key": "hvacOperationMode", "value": indigo.kHvacMode.Cool})
                    elif nest_hvac_mode == "heatCool":
                        keyValueList.append({"key": "hvacOperationMode", "value": indigo.kHvacMode.HeatCool})
                    else:  # Assume: nest_hvac_mode = 'off'
                        keyValueList.append({"key": "hvacOperationMode", "value": indigo.kHvacMode.Off})

            if (nest_dev.states["hvac_state"] != nest_hvac_state) or (command == API_COMMAND_START_DEVICE):
                keyValueList.append({"key": "hvac_state", "value": nest_hvac_state})
                # Set Indigo required internal states: hvacHeaterIsOn, hvacCoolerIsOn
                if nest_hvac_state == "heating":
                    keyValueList.append({"key": "hvacHeaterIsOn", "value": True})
                    keyValueList.append({"key": "hvacCoolerIsOn", "value": False})
                elif nest_hvac_state == "cooling":
                    keyValueList.append({"key": "hvacHeaterIsOn", "value": False})
                    keyValueList.append({"key": "hvacCoolerIsOn", "value": True})
                else:  # Assume: nest_hvac_state = 'off'
                    keyValueList.append({"key": "hvacHeaterIsOn", "value": False})
                    keyValueList.append({"key": "hvacCoolerIsOn", "value": False})



            if (nest_dev.states["target_temperature"] != nest_target_temperature) or (command == API_COMMAND_START_DEVICE) or hvac_mode_changed:
                keyValueList.append({"key": "target_temperature", "value": nest_target_temperature, "uiValue": nest_target_temperature_ui})
                if nest_can_cool:
                    if nest_hvac_mode == "cool":
                        keyValueList.append({"key": "setpointCool", "value": nest_target_temperature, "uiValue": nest_target_temperature_ui})
                        info_message_part_of = "cooling"
                    elif nest_hvac_mode == "heat":
                        keyValueList.append({"key": "setpointHeat", "value": nest_target_temperature, "uiValue": nest_target_temperature_ui})
                        info_message_part_of = "heating"
                    else:
                        info_message_part_of = ""
                else:
                    keyValueList.append({"key": "setpointHeat", "value": nest_target_temperature, "uiValue": nest_target_temperature_ui})
                    info_message_part_of = "heating"
                if (not nest_dev_props.get("hideSetpointBroadcast", False)) and info_message_part_of != "":
                    self.hubHandlerLogger.info(f"Received \"{nest_dev.name}\" set {info_message_part_of} setpoint to {nest_target_temperature_ui}")

            if nest_can_cool:
                if (nest_dev.states["target_cooling_threshold_temperature"] != nest_target_cooling_threshold_temperature) or (command == API_COMMAND_START_DEVICE) or hvac_mode_changed:
                    keyValueList.append({"key": "target_cooling_threshold_temperature", "value": nest_target_cooling_threshold_temperature,
                                         "uiValue": nest_target_cooling_threshold_temperature_ui})  # noqa
                    if nest_hvac_mode == "heatCool":
                        if nest_dev.states["setpointCool"] != nest_target_cooling_threshold_temperature or (command == API_COMMAND_START_DEVICE):
                            keyValueList.append({"key": "setpointCool", "value": nest_target_cooling_threshold_temperature})
                    if not nest_dev_props.get("hideSetpointBroadcast", False):
                        self.hubHandlerLogger.info(f"Received \"{nest_dev.name}\" set cooling threshold setpoint to {nest_target_cooling_threshold_temperature_ui}")

                if (nest_dev.states["target_heating_threshold_temperature"] != nest_target_heating_threshold_temperature) or (command == API_COMMAND_START_DEVICE) or hvac_mode_changed:
                    keyValueList.append({"key": "target_heating_threshold_temperature", "value": nest_target_heating_threshold_temperature,
                                         "uiValue": nest_target_heating_threshold_temperature_ui})  # noqa
                    if nest_hvac_mode == "heatCool":
                        if nest_dev.states["setpointHeat"] != nest_target_heating_threshold_temperature or (command == API_COMMAND_START_DEVICE):
                            keyValueList.append({"key": "setpointHeat", "value": nest_target_heating_threshold_temperature})
                    if not nest_dev_props.get("hideSetpointBroadcast", False):
                        self.hubHandlerLogger.info(f"Received \"{nest_dev.name}\" set heating threshold setpoint to {nest_target_heating_threshold_temperature_ui}")

            if (nest_dev.states["humidity_percent"] != nest_humidity_percent) or (command == API_COMMAND_START_DEVICE):
                keyValueList.append({"key": "humidity_percent", "value": nest_humidity_percent, "uiValue": nest_humidity_percent_ui})
                # Set Indigo required internal states: humidityInput1
                keyValueList.append({"key": "humidityInput1", "value": nest_humidity_percent, "uiValue": nest_humidity_percent_ui})
                if not nest_dev_props.get("hideHumidityBroadcast", False):
                    self.hubHandlerLogger.info(f"Received \"{nest_dev.name}\" humidity update to {nest_humidity_percent_ui}")

            # Humidifier Device Check
            if HUMIDIFIER_DEV_ID not in self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id]:
                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][HUMIDIFIER_DEV_ID] = 0
            nest_dev_humidifier_id = self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][HUMIDIFIER_DEV_ID]
            if nest_humidifier_active is None:
                if nest_dev_humidifier_id != 0:
                    # Force a restart of the Nest Thermostat device to update linked devices and remove linked Humidifier device
                    indigo.device.enable(nest_dev.id, value=False)  # disable
                    indigo.device.enable(nest_dev.id, value=True)  # enable
                    return
            else:
                nest_dev_humidifier_id = self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][HUMIDIFIER_DEV_ID]
                if nest_dev_humidifier_id == 0:
                    # Create Humidifier device
                    nest_dev_humidifier_id = self.create_humidifier_device(hub_id, nest_dev)

                nest_dev_humidifier = indigo.devices[nest_dev_humidifier_id]
                keyValueList_humidifier = list()
                current_humidifier_state_changed = False
                if (nest_dev_humidifier.states["humidifier_active"] != nest_humidifier_active) or (command == API_COMMAND_START_DEVICE):
                    keyValueList_humidifier.append({"key": "humidifier_active", "value": nest_humidifier_active})
                    # keyValueList.append({"key": "humidifier_active", "value": nest_humidifier_active})  # TODO: Implement this?
                if (nest_dev_humidifier.states["current_humidifier_state"] != nest_current_humidifier_state) or (command == API_COMMAND_START_DEVICE):
                    keyValueList_humidifier.append({"key": "current_humidifier_state", "value": nest_current_humidifier_state})
                    # keyValueList.append({"key": "current_humidifier_state", "value": nest_current_humidifier_state})  # TODO: Implement this for primary device?
                    current_humidifier_state_changed = True
                if (nest_dev_humidifier.states["target_humidity"] != nest_target_humidity) or (command == API_COMMAND_START_DEVICE):
                    keyValueList_humidifier.append({"key": "target_humidity", "value": nest_target_humidity})
                    keyValueList_humidifier.append({"key": "brightnessLevel", "value": int(nest_target_humidity)})
                    # keyValueList.append({"key": "target_humidity", "value": nest_target_humidity})  # TODO: Implement this for primary device?
                    current_humidifier_state_changed = True
                if (nest_dev_humidifier.states["humidity_percent"] != nest_humidity_percent) or (command == API_COMMAND_START_DEVICE):
                    keyValueList_humidifier.append({"key": "humidity_percent", "value": nest_humidity_percent})
                    # Note that the main Thermostat device has the humidity percent updated separately as not dependent on having a humidifier
                if len(keyValueList_humidifier) > 0:
                    if current_humidifier_state_changed:
                        # Set Indigo required internal states: hvacDehumidifierIsOn, hvacHumidifierIsOn  TODO: Implement this for primary device??
                        # Set kStateImageSel
                        if nest_current_humidifier_state == "humidifying":
                            # keyValueList.append({"key": "hvacHumidifierIsOn", "value": True})  # TODO: Implement this for primary device??
                            # keyValueList.append({"key": "hvacDehumidifierIsOn", "value": False})  # TODO: Implement this for primary device??
                            nest_dev_humidifier.updateStateImageOnServer(indigo.kStateImageSel.HumidifierOn)
                        elif nest_current_humidifier_state == "dehumidifying":
                            # keyValueList.append({"key": "hvacHumidifierIsOn", "value": False})  # TODO: Implement this for primary device??
                            # keyValueList.append({"key": "hvacDehumidifierIsOn", "value": True})  # TODO: Implement this for primary device??
                            nest_dev_humidifier.updateStateImageOnServer(indigo.kStateImageSel.DehumidifierOn)
                        else:
                            # keyValueList.append({"key": "hvacHumidifierIsOn", "value": False})  # TODO: Implement this for primary device??
                            # keyValueList.append({"key": "hvacDehumidifierIsOn", "value": False})  # TODO: Implement this for primary device??
                            nest_dev_humidifier.updateStateImageOnServer(indigo.kStateImageSel.HumidifierOff)
                        if not nest_dev_props.get("hideHumidifierBroadcast", False):
                            self.hubHandlerLogger.info(f"Received \"{nest_dev_humidifier.name}\" is {nest_current_humidifier_state}, target humidity is {nest_target_humidity_ui}")
                    nest_dev_humidifier.updateStatesOnServer(keyValueList_humidifier)

            # Fan Device Check
            if FAN_DEV_ID not in self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id]:
                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][FAN_DEV_ID] = 0
            nest_dev_fan_id = self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][FAN_DEV_ID]
            if nest_fan_running is None:
                if nest_dev_fan_id != 0:
                    # Force a restart of the Nest Thermostat device to update linked devices and remove linked Fan device
                    indigo.device.enable(nest_dev.id, value=False)  # disable
                    indigo.device.enable(nest_dev.id, value=True)  # enable
                    return
            else:
                nest_dev_fan_id = self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][FAN_DEV_ID]
                if nest_dev_fan_id == 0:
                    # Create Fan device
                    nest_dev_fan_id = self.create_fan_device(hub_id, nest_dev)

                nest_dev_fan = indigo.devices[nest_dev_fan_id]

                nest_fan_running_bool = self.derive_boolean(nest_fan_running)

                keyValueList_fan = list()
                if (nest_dev_fan.states["onOffState"] != nest_fan_running_bool) or (command == API_COMMAND_START_DEVICE):
                    keyValueList_fan.append({"key": "onOffState", "value": nest_fan_running_bool})
                    keyValueList.append({"key": "fan_running", "value": nest_fan_running_bool})
                    # Set Indigo required Primary device internal state: hvacFanIsOn
                    keyValueList.append({"key": "hvacFanIsOn", "value": nest_fan_running_bool})
                    if not nest_dev_props.get("hideFanBroadcast", False):
                        nest_fan_running_ui = ("OFF", "ON")[nest_fan_running_bool]
                        self.hubHandlerLogger.info(f"Received \"{nest_dev_fan.name}\" is {nest_fan_running_ui}")
                if len(keyValueList_fan) > 0:
                    if nest_fan_running_bool:
                        nest_dev_fan.updateStateImageOnServer(indigo.kStateImageSel.FanHigh)
                    else:
                        nest_dev_fan.updateStateImageOnServer(indigo.kStateImageSel.FanOff)
                    nest_dev_fan.updateStatesOnServer(keyValueList_fan)

            # Hot Water Device Check
            if HOT_WATER_DEV_ID not in self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id]:
                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][HOT_WATER_DEV_ID] = 0
            nest_dev_hot_water_id = self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][HOT_WATER_DEV_ID]
            if nest_hot_water_enabled is None:
                if nest_dev_hot_water_id != 0:
                    # Force a restart of the Nest Thermostat device to update linked devices and remove linked Hot Water device
                    indigo.device.enable(nest_dev.id, value=False)  # disable
                    indigo.device.enable(nest_dev.id, value=True)  # enable
                    return
            else:
                nest_dev_hot_water_id = self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][HOT_WATER_DEV_ID]
                if nest_dev_hot_water_id == 0:
                    # Create Hot_water device
                    nest_dev_hot_water_id = self.create_hot_water_device(hub_id, nest_dev)

                nest_dev_hot_water = indigo.devices[nest_dev_hot_water_id]

                nest_hot_water_enabled_bool = self.derive_boolean(nest_hot_water_enabled)

                keyValueList_hot_water = list()
                if nest_dev_hot_water.states["onOffState"] != nest_hot_water_enabled_bool:
                    keyValueList_hot_water.append({"key": "onOffState", "value": nest_hot_water_enabled_bool})
                    keyValueList.append({"key": "hot_water_enabled", "value": nest_hot_water_enabled_bool})
                    nest_hot_water_enabled_ui = ("OFF", "ON")[nest_hot_water_enabled_bool]
                    if not nest_dev_props.get("hideHotWaterBroadcast", False):
                        self.hubHandlerLogger.info(f"Received \"{nest_dev_hot_water.name}\" is {nest_hot_water_enabled_ui}")
                if len(keyValueList_hot_water) > 0:
                    nest_dev_hot_water.updateStateImageOnServer(indigo.kStateImageSel.Auto)
                    nest_dev_hot_water.updateStatesOnServer(keyValueList_hot_water)

            if len(keyValueList) > 0:
                nest_dev.updateStateImageOnServer(indigo.kStateImageSel.Auto)
                nest_dev.updateStatesOnServer(keyValueList)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def handle_devices_command_home_away_control(self, command, hub_id, nest_dev, nest_properties, keyValueList):
        try:
            # DEBUG SETUP START ...
            if "_starling_debug" in indigo.variables and indigo.variables["_starling_debug"].getValue(bool):
                starling_debug_home_away_control = indigo.variables["_starling_debug_home_away_control"].getValue(bool)
                if starling_debug_home_away_control:
                    nest_properties["homeState"] = indigo.variables["starling_home_away_control"].getValue(bool)
            # .. DEBUG SETUP END

            # Properties below already processed by invoking metheod:
            #   nest_id = nest_properties["id"]
            #   nest_name = nest_properties["name"]
            #   nest_serial_number = nest_properties["serialNumber"]
            #   nest_structure_name = nest_properties["structureName"]
            #   nest_type = nest_properties["type"]
            #   nest_where = nest_properties["where"]

            # Nest Protect Specific properties
            nest_home_state = nest_properties["homeState"]

            # Home Away control
            if (nest_dev.states["onOffState"] != nest_home_state) or (command == API_COMMAND_START_DEVICE):
                status = "Home" if nest_home_state else "Away"
                keyValueList.append({"key": "onOffState", "value": nest_home_state, "uiValue": status})
                keyValueList.append({"key": "status", "value": status})
                keyValueList.append({"key": "status_message", "value": f"{status} Mode"})

            k_state_image_sel = indigo.kStateImageSel.SensorOn if nest_home_state else indigo.kStateImageSel.SensorOff

            if len(keyValueList) > 0:
                nest_dev.updateStatesOnServer(keyValueList)
            if nest_dev.displayStateImageSel != k_state_image_sel:
                nest_dev.updateStateImageOnServer(k_state_image_sel)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def handle_devices_command_weather(self, command, hub_id, nest_dev, nest_properties, keyValueList):
        try:

            # Properties below already processed by invoking metheod:
            #   nest_id = nest_properties["id"]
            #   nest_name = nest_properties["name"]
            #   nest_serial_number = nest_properties["serialNumber"]
            #   nest_structure_name = nest_properties["structureName"]
            #   nest_type = nest_properties["type"]
            #   nest_where = nest_properties["where"]

            # Weather specific properties
            nest_current_temperature = nest_properties["currentTemperature"]
            nest_humidity_percent = nest_properties["humidityPercent"]
            nest_humidity_percent_ui = f"{nest_humidity_percent}%"

            nest_dev_props = nest_dev.pluginProps
            nest_display_temperature_units = nest_dev_props.get("temperature_units", "C")

            if nest_display_temperature_units == "F":
                nest_current_temperature = int(((float(nest_current_temperature) * 9) / 5) + 32.0)
                nest_current_temperature_ui = f"{nest_current_temperature}°F"
            else:
                nest_current_temperature = round(nest_current_temperature, 1)
                nest_current_temperature_ui = f"{nest_current_temperature}°C"

            if (nest_dev.states["current_temperature"] != nest_current_temperature) or (command == API_COMMAND_START_DEVICE):
                keyValueList.append({"key": "current_temperature", "value": nest_current_temperature, "uiValue": nest_current_temperature_ui})
                keyValueList.append({"key": "sensorValue", "value": nest_current_temperature, "uiValue": nest_current_temperature_ui})
                if not nest_dev_props.get("hideTemperatureBroadcast", False):
                    self.hubHandlerLogger.info(f"Received \"{nest_dev.name}\" temperature update to {nest_current_temperature_ui}")

            # Humidity Device Check
            if HUMIDITY_DEV_ID in self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id]:
                nest_dev_humidity_id = self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][HUMIDITY_DEV_ID]
            else:
                nest_dev_humidity_id = 0
            if nest_dev_humidity_id == 0:
                # Create Humidity device
                nest_dev_humidity_id = self.create_humidity_sensor_device(hub_id, nest_dev)
            nest_dev_humidity = indigo.devices[nest_dev_humidity_id]
            keyValueList_humidity = list()

            if (nest_dev_humidity.states["humidity_percent"] != nest_humidity_percent) or (command == API_COMMAND_START_DEVICE):
                keyValueList_humidity.append({"key": "humidity_percent", "value": nest_humidity_percent, "uiValue": nest_humidity_percent_ui})
                # Set Indigo required internal states: humidityInput1
                keyValueList_humidity.append({"key": "sensorValue", "value": nest_humidity_percent, "uiValue": nest_humidity_percent_ui})
                if not nest_dev_props.get("hideHumidityBroadcast", False):
                    self.hubHandlerLogger.info(f"Received \"{nest_dev_humidity.name}\" humidity update to {nest_humidity_percent_ui}")

            if len(keyValueList_humidity) > 0:
                nest_dev_humidity.updateStatesOnServer(keyValueList_humidity)
            if len(keyValueList) > 0:
                nest_dev.updateStateImageOnServer(indigo.kStateImageSel.Auto)
                nest_dev.updateStatesOnServer(keyValueList)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def determine_secondary_device_id(self, dev_id, secondary_dev_type_id):
        try:
            dev_id_list = indigo.device.getGroupList(dev_id)
            secondary_dev_id = 0
            if len(dev_id_list) > 1:
                for grouped_dev_id in dev_id_list:
                    if grouped_dev_id != dev_id and indigo.devices[grouped_dev_id].deviceTypeId == secondary_dev_type_id:
                        secondary_dev_id = grouped_dev_id
                        break
            return secondary_dev_id

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_decimal_places(self, field, decimal_places, units, space_before_units):
        try:
            units_plus_optional_space = u" {0}".format(units) if space_before_units else u"{0}".format(units)  # noqa [Duplicated code fragment!]
            if decimal_places == 0:
                return int(field), u"{0}{1}".format(int(field), units_plus_optional_space)
            else:
                value = round(field, decimal_places)

                uiValue = u"{{0:.{0}f}}{1}".format(decimal_places, units_plus_optional_space).format(field)

                return value, uiValue

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def access_starling_hub(self, starling_hub_dev, control_api, starling_command):
        try:
            # Connect to Starling Hub

            previous_status_message = starling_hub_dev.states["status_message"]

            props = starling_hub_dev.pluginProps
            ip_address = props.get("starling_hub_ip", "127.0.0.1")  # Should be in format "nnn.nnn.nnn.nnn"
            if props.get("starling_hub_ssl_tls", True):
                https_ip = ip_address.split(".")
                https_ip_1 = https_ip[0]
                https_ip_2 = https_ip[1]
                https_ip_3 = https_ip[2]
                https_ip_4 = https_ip[3]
                self.requests_prefix = f"https://{https_ip_1}-{https_ip_2}-{https_ip_3}-{https_ip_4}.local.starling.direct:3443/api/connect/v1/"
            else:
                self.requests_prefix = f"http://{ip_address}:3080/api/connect/v1/"  # noqa [http links are not secure]
            api_key = props.get("api_key", u"not_set_in_plugin")
            self.requests_suffix = f"?key={api_key}"
            requests_string = f"{self.requests_prefix}{starling_command}{self.requests_suffix}"

            # print(f"access_starling_hub Request String: {requests_string}")

            error_code = None
            error_message_ui = ""
            try:
                status_code = -1
                reply = requests.get(requests_string, timeout=5)
                reply.raise_for_status()
                # print(f"Reply Status: {reply.status_code}, Text: {reply.text}")
                status_code = reply.status_code
                if status_code == 200:
                    pass
                elif status_code == 400 or status_code == 401:
                    error_details = reply.json()
                    error_code = error_details["code"]
                    error_message_ui = error_details["message"]
                elif status_code == 404:
                    error_code = "Not Found"
                    error_message_ui = "Starling Hub not found"
                else:
                    error_code = "Unknown"
                    error_message_ui = "unknown connection error"
            except requests.exceptions.HTTPError as error_message:
                error_code = "HTTP Error"
                error_message_ui = f"Access Starling Hub failed: {error_message}"
                # print(f"HTTP ERROR: {error_message}")
                if error_code != previous_status_message:
                    self.hubHandlerLogger.error(error_message_ui)
                return "Error", [error_code, error_message_ui]
            except requests.exceptions.Timeout as error_message:
                error_code = "Timeout Error"
                error_message_ui = f"Access Starling Hub failed with a timeout error. Retrying . . ."
                if error_code != previous_status_message:
                    self.hubHandlerLogger.error(error_message_ui)
                return "Error", [error_code, error_message_ui]
            except requests.exceptions.ConnectionError as error_message:
                error_code = "Connection Error"
                error_message_ui = f"Access Starling Hub failed with a connection error. Retrying . . ."
                if error_code != previous_status_message:
                    self.hubHandlerLogger.error(error_message_ui)
                return "Error", [error_code, error_message_ui]
            except requests.exceptions.RequestException as error_message:
                error_code = "OOps: Unknown error"
                if error_code != previous_status_message:
                    error_message_ui = f"Access Starling Hub failed with an unknown error. Retrying . . ."
                    self.hubHandlerLogger.info(error_message_ui)
                return "Error", [error_code, error_message_ui]

            if status_code == 200:
                reply = reply.json()

                # Check Filter
                if FILTERS in self.globals:
                    if len(self.globals[FILTERS]) > 0 and self.globals[FILTERS] != ["-0-"]:
                        self.nest_filter_log_processing(starling_hub_dev.id, starling_hub_dev.name, control_api, reply)

                status = "OK"
                return status, reply  # noqa [reply might be referenced before assignment]

            else:
                # TODO: Sort this out!
                status = "Error"
                if error_message_ui is "":
                    self.hubHandlerLogger.error(f"Error [{status_code}] accessing Starling Hub '{starling_hub_dev.name}': {error_code}")
                else:
                    self.hubHandlerLogger.error(f"Error [{status_code}] accessing Starling Hub '{starling_hub_dev.name}': {error_code} - {error_message_ui}")
                return status, [error_code, error_message_ui]

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def nest_filter_log_processing(self, hub_id, hub_name, control_api, reply):
        try:
            log_nest_msg = False  # Assume Nest message should NOT be logged
            # Check if MQTT message filtering required
            if FILTERS in self.globals:
                if len(self.globals[FILTERS]) > 0 and self.globals[FILTERS] != ["-0-"]:
                    if self.globals[FILTERS] == ["-1-"]:
                        log_nest_msg = True
                    if self.globals[FILTERS] == ["-2-"]:
                        if control_api in (GET_CONTROL_API_STATUS, GET_CONTROL_API_DEVICES):
                            log_nest_msg = True
                    else:
                        if control_api == GET_CONTROL_API_DEVICES_ID:
                            # self.hubHandlerLogger.info(f"REPLY [{type(reply)}: {reply}")
                            nest_id = reply["properties"]["id"]
                            nest_filter = f"{hub_id}|||{nest_id}"
                            if nest_filter in self.globals[FILTERS]:
                                log_nest_msg = True
            if log_nest_msg:
                self.hubHandlerLogger.starling_api(f"Received message from '{hub_name}':{reply}")  # noqa [Unresolved attribute reference]

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def set_hvac_mode(self, nest_device_id, hvac_mode_translated, new_indigo_hvac_mode):
        try:
            pass
            starling_hub_dev = indigo.devices[self.starling_hub_device_id]

            nest_dev = indigo.devices[nest_device_id]

            nest_device_command = f"devices/{nest_dev.address}"

            hvac_mode_for_api = {"hvacMode": hvac_mode_translated}

            status, result = self.update_starling_hub(starling_hub_dev, nest_device_command, hvac_mode_for_api)

            if status != "OK":
                error_code = result[0]
                # error_message = result[1]
                keyValueList = [
                    {"key": "status", "value": "Disconnected"},
                    {"key": "status_message", "value": error_code}
                ]
                nest_dev.updateStatesOnServer(keyValueList)
                nest_dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                return

            self.hubHandlerLogger.debug(f"Starling API: Status={status}, Result='{result}'")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def set_thermostat_temperature(self, command, nest_device_id, target_temperature, state_key, log_action_name):
        try:
            pass
            starling_hub_dev = indigo.devices[self.starling_hub_device_id]

            nest_dev = indigo.devices[nest_device_id]
            nest_dev_props = nest_dev.pluginProps

            temperature_units = nest_dev.states["display_temperature_units"]
            # Note that updates to the Starling Hub must always be done in centigrade, so need to be converted if Fahrenheit
            if temperature_units == "F":
                nest_target_temperature_converted = round(float(((float(target_temperature) - 32.0) * 5.0) / 9.0), 1)
                nest_target_temperature_ui = f"{target_temperature}°F"
            else:
                nest_target_temperature_converted = target_temperature
                nest_target_temperature_ui = f"{target_temperature:.1f}°C"

            if nest_target_temperature_converted < 9.0:
                nest_target_temperature_converted = 9.0  # set to Nest Thermostat minimum setpoint value
            elif nest_target_temperature_converted > 32.0:
                nest_target_temperature_converted = 32.0  # set to Nest Thermostat maximum setpoint value

            nest_device_command = f"devices/{nest_dev.address}"

            # Update dependant on HVAC state

            indigo_device_state = state_key  # One of "setpointHeat" or "setpointCool"
            if command == SET_TARGET_TEMPERATURE:
                api_property = "targetTemperature"
                plugin_device_state = "target_temperature"
                ui_state = "Thermostat Setpoint"
            elif command == SET_TARGET_COOLING_THRESHOLD_TEMPERATURE:
                api_property = "targetCoolingThresholdTemperature"
                plugin_device_state = "target_cooling_threshold_temperature"
                ui_state = "Thermostat Cooling Setpoint"
            elif command == SET_TARGET_HEATING_THRESHOLD_TEMPERATURE:
                api_property = "targetHeatingThresholdTemperature"
                plugin_device_state = "target_heating_threshold_temperature"
                ui_state = "Thermostat Heating Setpoint"
            else:
                return

            thermostat_temperature_for_api = {api_property: nest_target_temperature_converted}
            status, result = self.update_starling_hub(starling_hub_dev, nest_device_command, thermostat_temperature_for_api)

            if status != "OK":
                error_code = result[0]
                # error_message = result[1]
                keyValueList = [
                    {"key": "status", "value": "Disconnected"},
                    {"key": "status_message", "value": error_code}
                ]
                nest_dev.updateStatesOnServer(keyValueList)
                nest_dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                self.hubHandlerLogger.error(f"send \"{nest_dev.name}\" {ui_state} {log_action_name} to {nest_target_temperature_ui} failed")
                return
            else:
                # All is good
                if nest_dev.states["target_temperature"] != target_temperature:
                    keyValueList = list()
                    keyValueList.append({"key": plugin_device_state, "value": target_temperature, "uiValue": nest_target_temperature_ui})
                    keyValueList.append({"key": indigo_device_state, "value": target_temperature, "uiValue": nest_target_temperature_ui})
                    nest_dev.updateStatesOnServer(keyValueList)

                    if not nest_dev_props.get("hideSetpointBroadcast", False):
                        self.hubHandlerLogger.info(f"sent \"{nest_dev.name}\" {log_action_name} to {nest_target_temperature_ui}")

                self.hubHandlerLogger.debug(f"Starling API: Status={status}, Result='{result}'")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def set_eco_mode(self, nest_device_id, eco_mode, eco_mode_ui):
        try:
            starling_hub_dev = indigo.devices[self.starling_hub_device_id]

            nest_dev = indigo.devices[nest_device_id]

            nest_device_command = f"devices/{nest_dev.address}"
            eco_mode_for_api = {"ecoMode": eco_mode}
            status, result = self.update_starling_hub(starling_hub_dev, nest_device_command, eco_mode_for_api)

            if status != "OK":
                error_code = result[0]
                # error_message = result[1]
                keyValueList = [
                    {"key": "status", "value": "Disconnected"},
                    {"key": "status_message", "value": error_code}
                ]
                nest_dev.updateStatesOnServer(keyValueList)
                nest_dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                self.hubHandlerLogger.error(f"send \"{nest_dev.name}\" {eco_mode_ui} Eco Mode failed")
                return
            else:
                # All is good
                self.hubHandlerLogger.info(f"sent \"{nest_dev.name}\" {eco_mode_ui} Eco Mode")

                self.hubHandlerLogger.debug(f"Starling API: Status={status}, Result='{result}'")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def set_fan_running(self, nest_device_id, fan_running, fan_running_ui):
        try:
            starling_hub_dev = indigo.devices[self.starling_hub_device_id]

            nest_dev = indigo.devices[nest_device_id]

            nest_device_command = f"devices/{nest_dev.address}"
            # fan_mode_state = ["false", "true"][fan_mode]
            fan_running_for_api = {"fanRunning": fan_running}
            status, result = self.update_starling_hub(starling_hub_dev, nest_device_command, fan_running_for_api)

            if status != "OK":
                error_code = result[0]
                # error_message = result[1]
                keyValueList = [
                    {"key": "status", "value": "Disconnected"},
                    {"key": "status_message", "value": error_code}
                ]
                nest_dev.updateStatesOnServer(keyValueList)
                nest_dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                self.hubHandlerLogger.error(f"send \"{nest_dev.name}\" {fan_running_ui} Fan failed")
                return
            else:
                # All is good
                self.hubHandlerLogger.info(f"sent \"{nest_dev.name}\" {fan_running_ui} Fan")

                self.hubHandlerLogger.debug(f"Starling API: Status={status}, Result='{result}'")

            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def set_home_away(self, nest_device_id, home_away):
        try:
            starling_hub_dev = indigo.devices[self.starling_hub_device_id]

            nest_dev = indigo.devices[nest_device_id]

            nest_device_command = f"devices/{nest_dev.address}"
            home_away_for_api = {"homeState": home_away}
            status, result = self.update_starling_hub(starling_hub_dev, nest_device_command, home_away_for_api)

            home_away__ui = "Home Mode" if home_away else "Away Mode"

            if status != "OK":
                error_code = result[0]
                # error_message = result[1]
                keyValueList = [
                    {"key": "status", "value": "Disconnected"},
                    {"key": "status_message", "value": error_code}
                ]
                nest_dev.updateStatesOnServer(keyValueList)
                nest_dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                self.hubHandlerLogger.error(f"send \"{nest_dev.name}\" set {home_away__ui} failed")
                return
            else:
                # All is good
                self.hubHandlerLogger.info(f"sent \"{nest_dev.name}\" set {home_away__ui}")

                self.hubHandlerLogger.debug(f"Starling API: Status={status}, Result='{result}'")

            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def set_hot_water(self, nest_device_id, hot_water_enabled, hot_water_ui):
        try:
            starling_hub_dev = indigo.devices[self.starling_hub_device_id]

            nest_dev = indigo.devices[nest_device_id]

            nest_device_command = f"devices/{nest_dev.address}"
            hot_water_enabled_for_api = {"hotWaterEnabled": hot_water_enabled}
            status, result = self.update_starling_hub(starling_hub_dev, nest_device_command, hot_water_enabled_for_api)

            if status != "OK":
                error_code = result[0]
                # error_message = result[1]
                keyValueList = [
                    {"key": "status", "value": "Disconnected"},
                    {"key": "status_message", "value": error_code}
                ]
                nest_dev.updateStatesOnServer(keyValueList)
                nest_dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                self.hubHandlerLogger.error(f"send \"{nest_dev.name}\" {hot_water_ui} Hot Water boost failed")
                return
            else:
                # All is good
                self.hubHandlerLogger.info(f"sent \"{nest_dev.name}\" {hot_water_ui} Hot Water boost")

                self.hubHandlerLogger.debug(f"Starling API: Status={status}, Result='{result}'")

            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def set_humidifier(self, nest_device_id, humidifier_active, humidifier_ui):
        try:
            starling_hub_dev = indigo.devices[self.starling_hub_device_id]

            nest_dev = indigo.devices[nest_device_id]

            nest_device_command = f"devices/{nest_dev.address}"
            humidifier_active_for_api = {"humidifierActive ": humidifier_active}
            status, result = self.update_starling_hub(starling_hub_dev, nest_device_command, humidifier_active_for_api)

            if status != "OK":
                error_code = result[0]
                # error_message = result[1]
                keyValueList = [
                    {"key": "status", "value": "Disconnected"},
                    {"key": "status_message", "value": error_code}
                ]
                nest_dev.updateStatesOnServer(keyValueList)
                nest_dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                self.hubHandlerLogger.error(f"send \"{nest_dev.name}\" {humidifier_ui} Humidifier failed")
                return
            else:
                # All is good
                self.hubHandlerLogger.info(f"sent \"{nest_dev.name}\" {humidifier_ui} Humidifier")

                self.hubHandlerLogger.debug(f"Starling API: Status={status}, Result='{result}'")

            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def set_humidifier_level(self, nest_device_id, humidifier_target_level, humidifier_ui):
        try:
            starling_hub_dev = indigo.devices[self.starling_hub_device_id]

            nest_dev = indigo.devices[nest_device_id]

            nest_device_command = f"devices/{nest_dev.address}"
            humidifier_active_for_api = {"targetHumidity ": humidifier_target_level}
            status, result = self.update_starling_hub(starling_hub_dev, nest_device_command, humidifier_active_for_api)

            if status != "OK":
                error_code = result[0]
                # error_message = result[1]
                keyValueList = [
                    {"key": "status", "value": "Disconnected"},
                    {"key": "status_message", "value": error_code}
                ]
                nest_dev.updateStatesOnServer(keyValueList)
                nest_dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                self.hubHandlerLogger.error(f"send \"{nest_dev.name}\" {humidifier_ui} failed")
                return
            else:
                # All is good

                self.hubHandlerLogger.info(f"sent \"{nest_dev.name}\" {humidifier_ui}")

                self.hubHandlerLogger.debug(f"Starling API: Status={status}, Result='{result}'")

                # DEBUG SETUP START ...
                if "_starling_debug" in indigo.variables and indigo.variables["_starling_debug"].getValue(bool):
                    starling_debug_thermostat = indigo.variables["_starling_debug_thermostat"].getValue(bool)
                    if starling_debug_thermostat:
                        if indigo.variables["starling_humidifier_enabled"].getValue(bool):
                            var_humidifier_target_level = f"{humidifier_target_level}"
                            indigo.variable.updateValue("starling_humidifier_target_humidity", value=var_humidifier_target_level)
                # .. DEBUG SETUP END

            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def update_starling_hub(self, starling_hub_dev, starling_command, starling_properties):
        try:
            # Connect to Starling Hub

            props = starling_hub_dev.pluginProps
            ip_address = props.get("starling_hub_ip", "127.0.0.1")  # Should be in format "nnn.nnn.nnn.nnn"
            if props.get("starling_hub_ssl_tls", True):
                https_ip = ip_address.split(".")
                https_ip_1 = https_ip[0]
                https_ip_2 = https_ip[1]
                https_ip_3 = https_ip[2]
                https_ip_4 = https_ip[3]
                self.requests_prefix = f"https://{https_ip_1}-{https_ip_2}-{https_ip_3}-{https_ip_4}.local.starling.direct:3443/api/connect/v1/"
            else:
                self.requests_prefix = f"http://{ip_address}:3080/api/connect/v1/"  # noqa [http links are not secure]
            api_key = props.get("api_key", u"not_set_in_plugin")
            self.requests_suffix = f"?key={api_key}"
            requests_string = f"{self.requests_prefix}{starling_command}{self.requests_suffix}"

            # print(f"update_starling_hub Request String: {requests_string}, Properties [{type(starling_properties)}]: {starling_properties}")

            error_code = None
            error_message = None

            try:
                self.hubHandlerLogger.starling_api(f"Sending message to '{starling_hub_dev.name}':{requests_string} | {starling_properties}")  # noqa [Unresolved attribute reference]
                reply = requests.post(requests_string, json=starling_properties, timeout=5)
                # print(f"Reply Status: {reply.status_code}, Text: {reply.text}")
                status_code = reply.status_code
                if status_code == 200:
                    # self.hubHandlerLogger.starling_api(f"Received message from '{starling_hub_dev.name}':{reply}")  # noqa [Unresolved attribute reference]
                    pass
                elif status_code == 400 or status_code == 401:
                    error_details = reply.json()
                    error_code = error_details["code"]
                    error_message = error_details["message"]
                elif status_code == 404:
                    error_code = "Not Found"
                    error_message = "Starling Hub not found"
                else:
                    error_code = "Unknown"
                    error_message = "unknown connection error"
            except Exception as error_message:
                status_code = -1
                error_code = "Unknown"
                error_message = error_message

            if status_code == 200:
                status = "OK"
                return status, reply.json()  # noqa [reply might be referenced before assignment]
            else:
                status = "Error"
                if error_message is None:
                    self.hubHandlerLogger.error(f"Error [{status_code}] accessing Starling Hub '{starling_hub_dev.name}': {error_code}")
                else:
                    self.hubHandlerLogger.error(f"Error [{status_code}] accessing Starling Hub '{starling_hub_dev.name}': {error_code}\n{error_message}")
                return status, [error_code, error_message]

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def derive_boolean(self, value):
        try:
            if type(value) == bool:
                return value
            boolean_value = False
            if value in ("True", "true"):
                boolean_value = True
            elif value in ("False", "false"):
                boolean_value = False
            else:
                self.hubHandlerLogger.debug(f"Derive Boolean Error: Value to be derived [Type is {type(value)}] = '{value}'")

            return boolean_value

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def derive_nest_deviceTypeId(self, nest_type):
        try:
            if nest_type == "protect":
                return "nestProtect"
            if nest_type == "thermostat":
                return "nestThermostat"
            if nest_type == "thermostat":
                return "nestTempSensor"
            if nest_type == "cam":
                return "nestCam"
            if nest_type == "guard":
                return "nestGuard"
            if nest_type == "detect":
                return "nestDetect"
            if nest_type == "lock":
                return "nestLock"
            if nest_type == "home_away_control":
                return "nestHomeAwayControl"
            if nest_type == "weather":
                return "nestWeather"

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement
            return ""

    def create_humidifier_device(self, hub_id, primary_dev):
        try:
            # Humidifier device missing - create it
            props_dict = dict()
            props_dict["member_of_device_group"] = True
            props_dict["linkedPrimaryIndigoDevice"] = primary_dev.name
            props_dict["associatedNestDeviceId"] = primary_dev.address
            props_dict["SupportsOnState"] = True
            props_dict["AllowOnStateChange"] = True
            props_dict["SupportsStatusRequest"] = False
            props_dict["SupportsSensorValue"] = False
            props_dict["AllowSensorValueChange"] = False
            props_dict["NumHumidityInputs"] = 1
            props_dict["supportsHumidityReporting"] = True

            secondary_name = f"{primary_dev.name} [HUMIDIFIER]"  # Create default name
            # Check name is unique and if not, make it so
            if secondary_name in indigo.devices:
                name_check_count = 1
                while True:
                    check_name = f"{secondary_name}_{name_check_count}"
                    if check_name not in indigo.devices:
                        secondary_name = check_name
                        break
                    name_check_count += 1

            secondary_dev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                                                 address=primary_dev.address,
                                                 description="",
                                                 name=secondary_name,
                                                 folder=primary_dev.folderId,
                                                 pluginId=self.globals[PLUGIN_INFO][PLUGIN_ID],
                                                 deviceTypeId="nestThermostatHumidifier",
                                                 groupWithDevice=primary_dev.id,
                                                 props=props_dict)

            # Manually need to set the model and subModel names (for UI only)
            secondary_dev_id = secondary_dev.id
            secondary_dev = indigo.devices[secondary_dev_id]  # Refresh Indigo Device to ensure groupWith Device isn't removed
            secondary_dev.subType = indigo.kDimmerDeviceSubType.PlugIn + ",ui=Humidifier"
            secondary_dev.replaceOnServer()

            self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][primary_dev.id][HUMIDIFIER_DEV_ID] = secondary_dev_id
            self.globals[INDIGO_DEVICE_TO_HUB][secondary_dev_id] = hub_id

            return secondary_dev_id

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def create_fan_device(self, hub_id, primary_dev):
        try:
            props_dict = dict()
            props_dict["member_of_device_group"] = True
            props_dict["linkedPrimaryIndigoDevice"] = primary_dev.name
            props_dict["associatedNestDeviceId"] = primary_dev.address
            props_dict["SupportsOnState"] = True
            props_dict["AllowOnStateChange"] = True
            props_dict["SupportsStatusRequest"] = False
            props_dict["SupportsSensorValue"] = False
            props_dict["AllowSensorValueChange"] = False

            secondary_name = f"{primary_dev.name} [FAN]"  # Create default name
            # Check name is unique and if not, make it so
            if secondary_name in indigo.devices:
                name_check_count = 1
                while True:
                    check_name = f"{secondary_name}_{name_check_count}"
                    if check_name not in indigo.devices:
                        secondary_name = check_name
                        break
                    name_check_count += 1

            secondary_dev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                                                 address=primary_dev.address,
                                                 description="",
                                                 name=secondary_name,
                                                 folder=primary_dev.folderId,
                                                 pluginId=self.globals[PLUGIN_INFO][PLUGIN_ID],
                                                 deviceTypeId="nestThermostatFan",
                                                 groupWithDevice=primary_dev.id,
                                                 props=props_dict)

            # Manually need to set the model and subModel names (for UI only)
            secondary_dev_id = secondary_dev.id
            secondary_dev = indigo.devices[secondary_dev_id]  # Refresh Indigo Device to ensure groupWith Device isn't removed
            secondary_dev.subType = indigo.kRelayDeviceSubType.PlugIn + ",ui=Fan"
            secondary_dev.replaceOnServer()

            self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][primary_dev.id][FAN_DEV_ID] = secondary_dev_id
            self.globals[INDIGO_DEVICE_TO_HUB][secondary_dev_id] = hub_id

            return secondary_dev_id

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def create_hot_water_device(self, hub_id, primary_dev):
        try:
            props_dict = dict()
            props_dict["member_of_device_group"] = True
            props_dict["linkedPrimaryIndigoDevice"] = primary_dev.name
            props_dict["associatedNestDeviceId"] = primary_dev.address
            props_dict["SupportsOnState"] = True
            props_dict["AllowOnStateChange"] = True
            props_dict["SupportsStatusRequest"] = False
            props_dict["SupportsSensorValue"] = False
            props_dict["AllowSensorValueChange"] = False

            secondary_name = f"{primary_dev.name} [HOT WATER]"  # Create default name
            # Check name is unique and if not, make it so
            if secondary_name in indigo.devices:
                name_check_count = 1
                while True:
                    check_name = f"{secondary_name}_{name_check_count}"
                    if check_name not in indigo.devices:
                        secondary_name = check_name
                        break
                    name_check_count += 1

            secondary_dev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                                                 address=primary_dev.address,
                                                 description="",
                                                 name=secondary_name,
                                                 folder=primary_dev.folderId,
                                                 pluginId=self.globals[PLUGIN_INFO][PLUGIN_ID],
                                                 deviceTypeId="nestThermostatHotWater",
                                                 groupWithDevice=primary_dev.id,
                                                 props=props_dict)

            # Manually need to set the model and subModel names (for UI only)
            secondary_dev_id = secondary_dev.id
            secondary_dev = indigo.devices[secondary_dev_id]  # Refresh Indigo Device to ensure groupWith Device isn't removed
            secondary_dev.subType = indigo.kRelayDeviceSubType.PlugIn + ",ui=Hot Water"
            secondary_dev.replaceOnServer()

            self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][primary_dev.id][HOT_WATER_DEV_ID] = secondary_dev_id
            self.globals[INDIGO_DEVICE_TO_HUB][secondary_dev_id] = hub_id

            return secondary_dev_id

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def create_co_sensor_device(self, hub_id, primary_dev):
        try:
            props_dict = dict()
            props_dict["member_of_device_group"] = True
            props_dict["linkedPrimaryIndigoDevice"] = primary_dev.name
            props_dict["associatedNestDeviceId"] = primary_dev.address
            props_dict["SupportsOnState"] = True
            props_dict["AllowOnStateChange"] = True
            props_dict["SupportsStatusRequest"] = False
            props_dict["SupportsSensorValue"] = False
            props_dict["AllowSensorValueChange"] = False

            secondary_name = f"{primary_dev.name} [CO]"  # Create default name
            # Check name is unique and if not, make it so
            if secondary_name in indigo.devices:
                name_check_count = 1
                while True:
                    check_name = f"{secondary_name}_{name_check_count}"
                    if check_name not in indigo.devices:
                        secondary_name = check_name
                        break
                    name_check_count += 1

            secondary_dev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                                                 address=primary_dev.address,
                                                 description="",
                                                 name=secondary_name,
                                                 folder=primary_dev.folderId,
                                                 pluginId=self.globals[PLUGIN_INFO][PLUGIN_ID],
                                                 deviceTypeId="nestProtectCo",
                                                 groupWithDevice=primary_dev.id,
                                                 props=props_dict)

            # Manually need to set the model and subModel names (for UI only)
            secondary_dev_id = secondary_dev.id
            secondary_dev = indigo.devices[secondary_dev_id]  # Refresh Indigo Device to ensure groupWith Device isn't removed
            secondary_dev.subType = indigo.kRelayDeviceSubType.PlugIn + ",ui=CO"
            secondary_dev.replaceOnServer()

            self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][primary_dev.id][CO_DEV_ID] = secondary_dev_id
            self.globals[INDIGO_DEVICE_TO_HUB][secondary_dev_id] = hub_id

            return secondary_dev_id

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def create_humidity_sensor_device(self, hub_id, primary_dev):
        try:
            props_dict = dict()
            props_dict["member_of_device_group"] = True
            props_dict["linkedPrimaryIndigoDevice"] = primary_dev.name
            props_dict["associatedNestDeviceId"] = primary_dev.address
            props_dict["SupportsOnState"] = False
            props_dict["AllowOnStateChange"] = False
            props_dict["SupportsStatusRequest"] = False
            props_dict["SupportsSensorValue"] = True
            props_dict["AllowSensorValueChange"] = False

            secondary_name = f"{primary_dev.name} [Humidity]"  # Create default name
            # Check name is unique and if not, make it so
            if secondary_name in indigo.devices:
                name_check_count = 1
                while True:
                    check_name = f"{secondary_name}_{name_check_count}"
                    if check_name not in indigo.devices:
                        secondary_name = check_name
                        break
                    name_check_count += 1

            secondary_dev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                                                 address=primary_dev.address,
                                                 description="",
                                                 name=secondary_name,
                                                 folder=primary_dev.folderId,
                                                 pluginId=self.globals[PLUGIN_INFO][PLUGIN_ID],
                                                 deviceTypeId="nestWeatherHumidity",
                                                 groupWithDevice=primary_dev.id,
                                                 props=props_dict)

            # Manually need to set the model and subModel names (for UI only)
            secondary_dev_id = secondary_dev.id
            secondary_dev = indigo.devices[secondary_dev_id]  # Refresh Indigo Device to ensure groupWith Device isn't removed
            secondary_dev.subType = indigo.kRelayDeviceSubType.PlugIn + ",ui=Humidity"
            secondary_dev.replaceOnServer()

            self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][primary_dev.id][HUMIDITY_DEV_ID] = secondary_dev_id
            self.globals[INDIGO_DEVICE_TO_HUB][secondary_dev_id] = hub_id

            return secondary_dev_id

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def create_motion_sensor_device(self, hub_id, primary_dev):
        try:
            props_dict = dict()
            props_dict["member_of_device_group"] = True
            props_dict["linkedPrimaryIndigoDevice"] = primary_dev.name
            props_dict["associatedNestDeviceId"] = primary_dev.address
            props_dict["SupportsOnState"] = True
            props_dict["AllowOnStateChange"] = False
            props_dict["SupportsStatusRequest"] = False
            props_dict["SupportsSensorValue"] = False
            props_dict["AllowSensorValueChange"] = False

            secondary_name = f"{primary_dev.name} [MOTION]"  # Create default name
            # Check name is unique and if not, make it so
            if secondary_name in indigo.devices:
                name_check_count = 1
                while True:
                    check_name = f"{secondary_name}_{name_check_count}"
                    if check_name not in indigo.devices:
                        secondary_name = check_name
                        break
                    name_check_count += 1

            secondary_dev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                                                 address=primary_dev.address,
                                                 description="",
                                                 name=secondary_name,
                                                 folder=primary_dev.folderId,
                                                 pluginId=self.globals[PLUGIN_INFO][PLUGIN_ID],
                                                 deviceTypeId="nestProtectMotion",
                                                 groupWithDevice=primary_dev.id,
                                                 props=props_dict)

            # Manually need to set the model and subModel names (for UI only)
            secondary_dev_id = secondary_dev.id
            secondary_dev = indigo.devices[secondary_dev_id]  # Refresh Indigo Device to ensure groupWith Device isn't removed
            secondary_dev.subType = indigo.kRelayDeviceSubType.PlugIn + ",ui=Motion"
            secondary_dev.replaceOnServer()

            props = primary_dev.ownerProps
            props["nest_occupancy_detected_enabled"] = True
            primary_dev.replacePluginPropsOnServer(props)

            self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][primary_dev.id][MOTION_DEV_ID] = secondary_dev_id
            self.globals[INDIGO_DEVICE_TO_HUB][secondary_dev_id] = hub_id

            return secondary_dev_id

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement
