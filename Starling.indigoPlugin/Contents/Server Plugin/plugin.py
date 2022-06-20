#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Starling Bridge - Plugin © Autolog 2022
#

# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import base64
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    raise ImportError("'cryptography' library missing.\n\n========> Run 'pip3 install cryptography' in Terminal window, then reload plugin. <========\n")

from datetime import datetime
import json
import os
import platform
import queue
import sys
import threading
import traceback

# ============================== Custom Imports ===============================
try:
    # noinspection PyUnresolvedReferences
    import indigo
    import requests  # noqa Included with Indigo package
except ImportError:
    pass

from constants import *  # Also imports logging
from hubHandler import Thread_Hub_Handler

# ================================== Header ===================================
__author__    = "Autolog"
__copyright__ = ""
__license__   = "MIT"
__build__     = "unused"
__title__     = "Starling Bridge Plugin for Indigo"
__version__   = "unused"


def encode(unencrypted_password):
    print(f"Encode, Argument: Unencrypted Password = {unencrypted_password}")

    internal_password = STARLING_INTERNAL_ENCRYPTION_PASSWORD  # Byte string
    print(f"Encode - Internal Password: {internal_password}")

    salt = os.urandom(16)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390000)
    key = base64.urlsafe_b64encode(kdf.derive(internal_password))
    print(f"Encode - Key: {key}")

    f = Fernet(key)

    unencrypted_password = unencrypted_password.encode()  # str -> b
    encrypted_password = f.encrypt(unencrypted_password)
    print(f"Encode - Encrypted Password: {encrypted_password}")

    return key, encrypted_password


def decode(key, encrypted_password):
    print(f"Decode, Arguments: Key='{key}', Encrypted Password='{encrypted_password}'")

    f = Fernet(key)
    unencrypted_password = f.decrypt(encrypted_password)

    print(f"Decode: Unencrypted Password = {unencrypted_password}")

    return unencrypted_password


HVAC_MODE_ENUM_TO_STR_MAP = {
    indigo.kHvacMode.Cool: "cool",
    indigo.kHvacMode.Heat: "heat",
    indigo.kHvacMode.HeatCool: "auto",
    indigo.kHvacMode.Off: "off"
    # indigo.kHvacMode.ProgramHeat: "program heat",
    # indigo.kHvacMode.ProgramCool: "program cool",
    # indigo.kHvacMode.ProgramHeatCool: "program auto"
}

FAN_MODE_ENUM_TO_STR_MAP = {
    indigo.kFanMode.AlwaysOn            : "always on",
    indigo.kFanMode.Auto                : "auto"
}


def _lookup_action_str_from_hvac_mode(hvac_mode):
    return HVAC_MODE_ENUM_TO_STR_MAP.get(hvac_mode, "unknown")


def _lookup_action_str_from_fan_mode(fan_mode):
    return FAN_MODE_ENUM_TO_STR_MAP.get(fan_mode, "unknown")


# noinspection PyPep8Naming
class Plugin(indigo.PluginBase):

    def __init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs):
        super(Plugin, self).__init__(plugin_id, plugin_display_name, plugin_version, plugin_prefs)

        # Initialise dictionary to store plugin Globals
        self.globals = dict()

        self.globals[POLLING_SECONDS] = 5

        logging.addLevelName(LOG_LEVEL_STARLING_API, "starling_api")

        def starling_api(self, message, *args, **kws):  # noqa [Shadowing names from outer scope = self]
            self.log(LOG_LEVEL_STARLING_API, message, *args, **kws)

        logging.Logger.starling_api = starling_api

        # Initialise Indigo plugin info
        self.globals[PLUGIN_INFO] = {}
        self.globals[PLUGIN_INFO][PLUGIN_ID] = plugin_id
        self.globals[PLUGIN_INFO][PLUGIN_DISPLAY_NAME] = plugin_display_name
        self.globals[PLUGIN_INFO][PLUGIN_VERSION] = plugin_version
        self.globals[PLUGIN_INFO][PATH] = indigo.server.getInstallFolderPath()
        self.globals[PLUGIN_INFO][API_VERSION] = indigo.server.apiVersion
        self.globals[PLUGIN_INFO][ADDRESS] = indigo.server.address

        log_format = logging.Formatter("%(asctime)s.%(msecs)03d\t%(levelname)-12s\t%(name)s.%(funcName)-25s %(msg)s", datefmt="%Y-%m-%d %H:%M:%S")
        self.plugin_file_handler.setFormatter(log_format)
        self.plugin_file_handler.setLevel(LOG_LEVEL_INFO)  # Logging Level for plugin log file
        self.indigo_log_handler.setLevel(LOG_LEVEL_INFO)   # Logging level for Indigo Event Log

        self.logger = logging.getLogger("Plugin.Starling")

        # Setup store for Starling identified Nest devices
        self.globals[HUBS] = dict()
        self.globals[EVENT] = dict()
        self.globals[THREAD] = dict()
        self.globals[INDIGO_DEVICE_TO_HUB] = dict()
        self.globals[TRIGGERS_NEST_PROTECT] = dict()
        self.globals[TRIGGERS_NEST_PROTECTS_ALL] = dict()
        self.globals[ALERTS_IN_PROGRESS] = dict()

        self.globals[LIST_STARLING_HUBS] = set()
        self.globals[LIST_NEST_DEVICES] = set()
        self.globals[LIST_NEST_DEVICES_SELECTED] = False

        self.globals[FILTERS] = list()
        self.globals[FILTERABLE_DEVICES] = dict()

        # Initialise Queues area for Starling Hubs
        self.globals[QUEUES] = dict()

        # Set Plugin Config Values
        self.closed_prefs_config_ui(plugin_prefs, False)

    def display_plugin_information(self):
        try:
            def plugin_information_message():
                startup_message_ui = "Plugin Information:\n"
                startup_message_ui += f"{'':={'^'}80}\n"
                startup_message_ui += f"{'Plugin Name:':<30} {self.globals[PLUGIN_INFO][PLUGIN_DISPLAY_NAME]}\n"
                startup_message_ui += f"{'Plugin Version:':<30} {self.globals[PLUGIN_INFO][PLUGIN_VERSION]}\n"
                startup_message_ui += f"{'Plugin ID:':<30} {self.globals[PLUGIN_INFO][PLUGIN_ID]}\n"
                startup_message_ui += f"{'Indigo Version:':<30} {indigo.server.version}\n"
                startup_message_ui += f"{'Indigo License:':<30} {indigo.server.licenseStatus}\n"
                startup_message_ui += f"{'Indigo API Version:':<30} {indigo.server.apiVersion}\n"
                startup_message_ui += f"{'Architecture:':<30} {platform.machine()}\n"
                startup_message_ui += f"{'Python Version:':<30} {sys.version.split(' ')[0]}\n"
                startup_message_ui += f"{'Mac OS Version:':<30} {platform.mac_ver()[0]}\n"
                startup_message_ui += f"{'Plugin Process ID:':<30} {os.getpid()}\n"
                startup_message_ui += f"{'':={'^'}80}\n"
                return startup_message_ui

            self.logger.info(plugin_information_message())

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def exception_handler(self, exception_error_message, log_failing_statement):
        filename, line_number, method, statement = traceback.extract_tb(sys.exc_info()[2])[-1]
        module = filename.split('/')
        log_message = f"'{exception_error_message}' in module '{module[-1]}', method '{method}'"
        if log_failing_statement:
            log_message = log_message + f"\n   Failing statement [line {line_number}]: '{statement}'"
        else:
            log_message = log_message + f" at line {line_number}"
        self.logger.error(log_message)

    ########################################
    # Trigger (Event) handling
    ########################################

    def triggerStartProcessing(self, trigger):
        self.logger.debug(f"{trigger.name}: Adding Trigger")
        if trigger.pluginTypeId in ("alertDetected", "alertNoLongerDetected"):
            assert trigger.id not in self.globals[TRIGGERS_NEST_PROTECT]
            self.globals[TRIGGERS_NEST_PROTECT][trigger.id] = trigger
        elif trigger.pluginTypeId in ("alertDetectedAnyProtect", "alerttNoLongeDetectedAnyProtect"):
            assert trigger.id not in self.globals[TRIGGERS_NEST_PROTECTS_ALL]
            self.globals[TRIGGERS_NEST_PROTECTS_ALL][trigger.id] = trigger

    def triggerStopProcessing(self, trigger):
        self.logger.debug(f"{trigger.name}: Removing Trigger")
        if trigger.pluginTypeId in ("alertDetected", "alertNoLongerDetected"):
            assert trigger.id in self.globals[TRIGGERS_NEST_PROTECT]
            del self.globals[TRIGGERS_NEST_PROTECT][trigger.id]
        elif trigger.pluginTypeId in ("alertDetectedAnyProtect", "alerttNoLongeDetectedAnyProtect"):
            assert trigger.id in self.globals[TRIGGERS_NEST_PROTECTS_ALL]
            del self.globals[TRIGGERS_NEST_PROTECTS_ALL][trigger.id]

    def action_control_device(self, action, dev):
        try:
            if not dev.enabled:
                return

            hub_id = self.globals[INDIGO_DEVICE_TO_HUB][dev.id]

            if hub_id == 0:
                self.logger.error(f"Warning: Starling Hub id not defined for {dev.name}. Hub ID = {hub_id}")
                return

            if dev.deviceTypeId not in ("nestThermostatHotWater", "nestThermostatFan", "nestThermostatHumidifier", "nestHomeAwayControl"):
                return

            if action.deviceAction in (indigo.kDeviceAction.TurnOn, indigo.kDeviceAction.TurnOff, indigo.kDeviceAction.Toggle):
                if dev.deviceTypeId == "nestThermostatHotWater":
                    command_on_off_toggle = SET_HOT_WATER
                elif dev.deviceTypeId == "nestThermostatHumidifier":
                    command_on_off_toggle = SET_HUMIDIFIER
                elif dev.deviceTypeId == "nestThermostatFan":
                    command_on_off_toggle = SET_FAN
                elif dev.deviceTypeId == "nestHomeAwayControl":
                    command_on_off_toggle = SET_HOME_AWAY
                else:
                    return

                # ##### TURN ON | TURN OFF ######
                if action.deviceAction in (indigo.kDeviceAction.TurnOn, indigo.kDeviceAction.TurnOff):
                    turn_on_off_request = True if action.deviceAction == indigo.kDeviceAction.TurnOn else False
                    action_request_ui = f'turn {["off", "on"][turn_on_off_request]}'

                    self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_HIGH, command_on_off_toggle, [dev.id], [turn_on_off_request, action_request_ui]))

                # ##### TOGGLE ######
                elif action.deviceAction == indigo.kDeviceAction.Toggle:
                    toggle_request = not dev.onState
                    action_request_ui = f'toggle {["off", "on"][toggle_request]}'

                    self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_HIGH, command_on_off_toggle, [dev.id], [toggle_request, action_request_ui]))

            elif action.deviceAction in (indigo.kDeviceAction.SetBrightness, indigo.kDeviceAction.BrightenBy, indigo.kDeviceAction.DimBy):
                if dev.deviceTypeId == "nestThermostatHumidifier":
                    command_set_level = SET_HUMIDIFIER_LEVEL
                    device_ui = "humidification"
                else:
                    return

                # ##### SET LEVEL ######
                if action.deviceAction == indigo.kDeviceAction.SetBrightness:
                    new_target_level = int(action.actionValue)   # action.actionValue contains humidifier target level value (0 - 100)
                    action_ui = "set"
                    if new_target_level > 0:
                        if new_target_level > dev.brightness:
                            action_ui = "increase"
                        else:
                            action_ui = "reduce"
                    new_target_level_ui = f"{action_ui} {device_ui} level to {new_target_level}%"
                    self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_HIGH, command_set_level, [dev.id], [new_target_level, new_target_level_ui]))

                # ##### INCREASE LEVEL BY ######
                elif action.deviceAction == indigo.kDeviceAction.BrightenBy:
                    # if not dev.onState:
                    #     pass  # TODO: possibly turn on?
                    if dev.brightness < 100:
                        increase_level_by = int(action.actionValue)  # action.actionValue contains brightness increase value
                        new_target_level = dev.brightness + increase_level_by
                        if new_target_level > 100:
                            increase_level_by = new_target_level - 100
                            new_target_level = 100
                        new_target_level_ui = f"increase {device_ui} level by {increase_level_by}% to {new_target_level}%"
                        self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_HIGH, command_set_level, [dev.id], [new_target_level, new_target_level_ui]))
                    else:
                        self.logger.info(f"Ignoring increase level request for {dev.name} as device is already at the maximum level")

                # ##### DECREASE LEVEL BY ######
                elif action.deviceAction == indigo.kDeviceAction.DimBy:
                    # if not dev.onState:
                    #     pass  # TODO: possibly turn on?
                    if dev.brightness > 0:
                        decrease_level_by = int(action.actionValue)  # action.actionValue contains brightness decrease value
                        new_target_level = dev.brightness - decrease_level_by
                        if new_target_level < 0:
                            decrease_level_by = dev.brightness
                            new_target_level = 0
                        new_target_level_ui = f"decrease {device_ui} level by {decrease_level_by}% to {new_target_level}%"

                        self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_HIGH, command_set_level, [dev.id], [new_target_level, new_target_level_ui]))
                    else:
                        self.logger.info(f"Ignoring decrease level request for {dev.name} as device is already at the minimum level")
            else:
                self.logger.warning(f"Unhandled \"actionControlDevice\" action \"{action.deviceAction}\" for \"{dev.name}\"")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def action_control_thermostat(self, action, dev):
        try:
            if not dev.enabled:
                return

            ###### SET HVAC MODE ######
            if action.thermostatAction == indigo.kThermostatAction.SetHvacMode:
                self._handle_change_hvac_mode_action(dev, action.actionMode)

            ###### SET FAN MODE ######
            elif action.thermostatAction == indigo.kThermostatAction.SetFanMode:
                self._handle_change_fan_mode_action(dev, action.actionMode)

            ###### SET COOL SETPOINT ######
            elif action.thermostatAction == indigo.kThermostatAction.SetCoolSetpoint:
                new_setpoint = action.actionValue
                self._handle_change_setpoint_action(dev, new_setpoint, "change cool setpoint", "setpointCool")

            ###### SET HEAT SETPOINT ######
            elif action.thermostatAction == indigo.kThermostatAction.SetHeatSetpoint:
                new_setpoint = action.actionValue
                self._handle_change_setpoint_action(dev, new_setpoint, "change heat setpoint", "setpointHeat")

            ###### DECREASE/INCREASE COOL SETPOINT ######
            elif action.thermostatAction == indigo.kThermostatAction.DecreaseCoolSetpoint:
                new_setpoint = dev.coolSetpoint - action.actionValue
                self._handle_change_setpoint_action(dev, new_setpoint, "decrease cool setpoint", "setpointCool")

            elif action.thermostatAction == indigo.kThermostatAction.IncreaseCoolSetpoint:
                new_setpoint = dev.coolSetpoint + action.actionValue
                self._handle_change_setpoint_action(dev, new_setpoint, "increase cool setpoint", "setpointCool")

            ###### DECREASE/INCREASE HEAT SETPOINT ######
            elif action.thermostatAction == indigo.kThermostatAction.DecreaseHeatSetpoint:
                new_setpoint = dev.heatSetpoint - action.actionValue
                self._handle_change_setpoint_action(dev, new_setpoint, "decrease heat setpoint", "setpointHeat")

            elif action.thermostatAction == indigo.kThermostatAction.IncreaseHeatSetpoint:
                new_setpoint = dev.heatSetpoint + action.actionValue
                self._handle_change_setpoint_action(dev, new_setpoint, "increase heat setpoint", "setpointHeat")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    ######################
    # Process action request from Indigo Server to change a cool/heat setpoint.
    def _handle_change_setpoint_action(self, dev, new_setpoint, log_action_name, state_key):
        props = dev.pluginProps
        hub_id = int(props.get("starling_hub_indigo_id", 0))
        if hub_id == 0:
            self.logger.error(f"Warning: Starling Hub id not defined for {dev.name}")
            return

        if state_key == "setpointCool":
            # Command hardware module (dev) to change the cool setpoint to new_setpoint here:
            if dev.states["hvacOperationMode"] == indigo.kHvacMode.HeatCool:
                self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_HIGH, SET_TARGET_COOLING_THRESHOLD_TEMPERATURE, [dev.id], [new_setpoint, state_key, log_action_name]))
            elif dev.states["hvacOperationMode"] == indigo.kHvacMode.Cool:
                self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_HIGH, SET_TARGET_TEMPERATURE, [dev.id], [new_setpoint, state_key, log_action_name]))
            else:
                self.logger.warning(f"Setting Cool setpoint ignored for '{dev.name}' as only supported by an HVAC mode of 'Cool On' or 'Auto Heat/Cool'.")
        elif state_key == "setpointHeat":
            # Command hardware module (dev) to change the heat setpoint to new_setpoint here:
            if dev.states["hvacOperationMode"] == indigo.kHvacMode.HeatCool:
                self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_HIGH, SET_TARGET_HEATING_THRESHOLD_TEMPERATURE, [dev.id], [new_setpoint, state_key, log_action_name]))
            elif dev.states["hvacOperationMode"] == indigo.kHvacMode.Heat:
                self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_HIGH, SET_TARGET_TEMPERATURE, [dev.id], [new_setpoint, state_key, log_action_name]))
            else:
                self.logger.warning(f"Setting Heat setpoint ignored for '{dev.name}' as only supported by an HVAC mode of 'Heat On' or 'Auto Heat/Cool'.")

        # Indigo Device state updates and information message performed in hubHandler on receipt of queued message

    ######################
    # Process action request from Indigo Server to change main thermostat's main mode.
    def _handle_change_hvac_mode_action(self, dev, new_indigo_hvac_mode):
        props = dev.pluginProps
        hub_id = int(props.get("starling_hub_indigo_id", 0))
        if hub_id == 0:
            self.logger.error(f"Warning: Starling Hub id not defined for {dev.name}")
            return
        hvac_mode = _lookup_action_str_from_hvac_mode(new_indigo_hvac_mode)
        if not dev.states["can_cool"]:
            if new_indigo_hvac_mode in [indigo.kHvacMode.Cool, indigo.kHvacMode.HeatCool]:
                self.logger.warning(f"Setting HVAC Mode to '{hvac_mode}' ignored as not supported by {dev.name}")
                return
        hvac_mode_translated = "heatCool" if hvac_mode == "auto" else hvac_mode
        self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_HIGH, SET_HVAC_MODE, [dev.id], [hvac_mode_translated, new_indigo_hvac_mode]))
        send_success = True     # Set to False if it failed.
        if send_success:
            # If success then log that the command was successfully sent.
            self.logger.info(f"sent \"{dev.name}\" mode change to {hvac_mode}")

            # And then tell the Indigo Server to update the state.
            # if "hvacOperationMode" in dev.states:
            #
            # TODO: Make sure next four code lines aren't needed
            #
            #     keyValueList = list()
            #     keyValueList.append({"key": "hvacOperationMode", "value": new_indigo_hvac_mode})
            #     keyValueList.append({"key": "hvac_mode", "value": hvac_mode_translated})
            #     dev.updateStatesOnServer(keyValueList)
        else:
            # Else log failure but do NOT update state on Indigo Server.
            self.logger.error(f"send \"{dev.name}\" mode change to {hvac_mode} failed")

    def turnOnEcoMode(self,  action, dev):
        try:
            self.setEcoMode(dev, True)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def turnOffEcoMode(self, action, dev):
        try:
            self.setEcoMode(dev, False)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def setEcoMode(self, dev, eco_mode):
        try:
            props = dev.pluginProps
            hub_id = int(props.get("starling_hub_indigo_id", 0))
            if hub_id == 0:
                self.logger.error(f"Warning: Starling Hub id not defined for {dev.name}")
                return

            eco_mode_ui = "turn on" if eco_mode else "turn off"

            self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_HIGH, SET_ECO_MODE, [dev.id], [eco_mode, eco_mode_ui]))

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def action_control_universal(self, action, dev):
        try:
            if not dev.enabled:
                return

            self.logger.warning(f"Action '{action.deviceAction}' on device '{dev.name} is not supported by the plugin.")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def closed_device_config_ui(self, values_dict=None, user_cancelled=False, type_id="", dev_id=0):
        """
        Indigo method invoked after device configuration dialog is closed.

        -----
        :param values_dict:
        :param user_cancelled:
        :param type_id:
        :param dev_id:
        :return:
        """

        if dev_id not in indigo.devices:
            return

        dev = indigo.devices[int(dev_id)]

        try:
            if user_cancelled:
                self.logger.threaddebug(f"'closedDeviceConfigUi' called with userCancelled = {str(user_cancelled)}")
                return

            if type_id in ("nestProtect", "nestThermostat", "nestHomeAwayControl", "nestWeather"):
                starling_hub_device_id = int(values_dict.get("starling_hub_indigo_id", 0))
                if starling_hub_device_id > 0:
                    if dev_id not in self.globals[HUBS][starling_hub_device_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID]:
                            self.globals[HUBS][starling_hub_device_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev_id] = dict()
                            self.globals[HUBS][starling_hub_device_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev_id][NEST_ID] = values_dict.get("nest_id", "")
                            nest_id = values_dict["nest_id"]
                            self.globals[HUBS][starling_hub_device_id][NEST_DEVICES_BY_NEST_ID][nest_id] = dict()
                            self.globals[HUBS][starling_hub_device_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEV_ID] = dev_id
                            self.globals[HUBS][starling_hub_device_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEVICE_TYPE_ID] = dev.deviceTypeId
                            self.globals[HUBS][starling_hub_device_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_NAME] = values_dict["nest_name"]
                            self.globals[HUBS][starling_hub_device_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_WHERE] = values_dict["nest_where"]

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def closed_prefs_config_ui(self, values_dict=None, user_cancelled=False):
        try:
            if user_cancelled:
                return

            # The frequency of Starling Home Hub polling
            self.globals[POLLING_SECONDS] = int(values_dict.get("polling_seconds", 5))

            # Get required Event Log and Plugin Log logging levels
            plugin_log_level = int(values_dict.get("pluginLogLevel", LOG_LEVEL_INFO))
            event_log_level = int(values_dict.get("eventLogLevel", LOG_LEVEL_INFO))

            # Ensure following logging level messages are output
            self.indigo_log_handler.setLevel(LOG_LEVEL_INFO)
            self.plugin_file_handler.setLevel(LOG_LEVEL_INFO)

            # Output required logging levels  to logs
            # self.logger.info(f"Logging to Indigo Event Log at the '{LOG_LEVEL_TRANSLATION[event_log_level]}' level")
            # self.logger.info(f"Logging to Plugin Event Log at the '{LOG_LEVEL_TRANSLATION[plugin_log_level]}' level")

            # Now set required logging levels
            self.indigo_log_handler.setLevel(event_log_level)
            self.plugin_file_handler.setLevel(plugin_log_level)

            # Set Starling Hub Message Filter
            self.globals[FILTERS] = list()  # Initialise Starling filter dictionary
            nest_message_filter = values_dict.get("nestMessageFilter", ["-0-|||-- Don't Log Any Devices --"])
            log_message = "Filtering active for the following Nest device(s):"  # Not used if no logging required
            filtering_required = False

            spaces = " " * 35  # used to pad log messages

            if len(self.globals[FILTERABLE_DEVICES]) == 0:
                # Set from stored filterabe devices in values_dict
                self.globals[FILTERABLE_DEVICES] = json.loads(values_dict["filterable_devices"])
                # self.logger.info(f"FILTERABLE_DEVICES [JSON_LOADS]: {self.globals[FILTERABLE_DEVICES]}")

            if len(nest_message_filter) == 0:
                self.globals[FILTERS] = ["-0-"]
            else:
                for entry in nest_message_filter:
                    # self.logger.error(f"FILTER: {entry}")
                    starling_hub_id_string, nest_device_id = entry.split("|||")
                    if starling_hub_id_string == "-0-":  # Ignore '-- Don't Log Any Devices --'
                        self.globals[FILTERS] = ["-0-"]
                        break
                    elif starling_hub_id_string == "-1-":  # Ignore '-- Log All Devices --'
                        self.globals[FILTERS] = ["-1-"]
                        log_message = f"{log_message}\n{spaces}All Nest Devices"
                        filtering_required = True
                        break
                    elif starling_hub_id_string == "-2-":  # Ignore '-- Log Hub Device --'
                        self.globals[FILTERS] = ["-2-"]
                        log_message = f"{log_message}\n{spaces}Hub Device(s)"
                        filtering_required = True
                    else:
                        # starling_hub_id = int(starling_hub_id_string)
                        # starling_hub_name = indigo.devices[starling_hub_id].name
                        # name = self.globals[HUBS][starling_hub_id][NEST_DEVICES_BY_NEST_ID][nest_device_id][NEST_NAME]
                        # where = self.globals[HUBS][starling_hub_id][NEST_DEVICES_BY_NEST_ID][nest_device_id][NEST_WHERE]
                        # if where != "":
                        #     where = f"-{where}"
                        # nest_full_name = f"{name}{where}"

                        starling_hub_and_nest_device_name_ui = self.globals[FILTERABLE_DEVICES][entry]
                        self.globals[FILTERS].append(entry)
                        spaces = " " * 24
                        log_message = f"{log_message}\n{spaces}Nest Device: '{starling_hub_and_nest_device_name_ui}'"
                        filtering_required = True

            if filtering_required:
                self.logger.warning(f"{log_message}\n")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def filterListNestDevices(self, filter="", valuesDict=None, typeId="", targetId=0):  # noqa [parameter value is not used]
        try:
            nest_devices_list = list()
            self.globals[FILTERABLE_DEVICES] = dict()

            nest_devices_list.append(("-0-|||-- Don't Log Any Devices --", "-- Don't Log Any Nest Devices --"))
            nest_devices_list.append(("-1-|||-- Log All Devices --", "-- Log All Nest Devices --"))
            nest_devices_list.append(("-2-|||-- Log Hub Device(s) --", "-- Log Hub Device(s) --"))

            for hub_indigo_id in self.globals[HUBS].keys():
                hub_indigo_id_string = f"{hub_indigo_id}"
                hub_name = indigo.devices[hub_indigo_id].name
                for nest_id, nest_devices_details in self.globals[HUBS][hub_indigo_id][NEST_DEVICES_BY_NEST_ID].items():
                    name = nest_devices_details[NEST_NAME]
                    where = f"{nest_devices_details[NEST_WHERE]}"
                    if where != "":
                        where = f"-{where}"
                    nest_full_name = f"{name}{where}"
                    hub_and_nest_device_name_key = f"{hub_indigo_id_string}|||{nest_id}"
                    hub_and_nest_device_name_value = f"{hub_name} | {nest_full_name}"
                    nest_devices_list.append((hub_and_nest_device_name_key, hub_and_nest_device_name_value))

                    self.globals[FILTERABLE_DEVICES][hub_and_nest_device_name_key] = hub_and_nest_device_name_value

            return sorted(nest_devices_list, key=lambda name: name[1].lower())   # sort by hubitat device name
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def device_start_comm(self, dev):
        try:
            dev.stateListOrDisplayStateIdChanged()  # Ensure that latest devices.xml is being used
            
            # "thermostat", "temp_sensor", "protect", "cam", "guard", "detect", "lock", "home_away_control"

            # Check Device Type and invoke appropriate method to start it
            if dev.deviceTypeId == "starlingHub":
                self.device_start_comm_starling_hub(dev)
            elif dev.deviceTypeId == "nestProtect":
                self.device_start_comm_nest_protect(dev)
            elif dev.deviceTypeId == "nestThermostat":
                self.device_start_comm_nest_thermostat(dev)
            elif dev.deviceTypeId == "nestTempSensor":
                self.device_start_comm_nest_temp_sensor(dev)
            elif dev.deviceTypeId == "nestCam":
                self.device_start_comm_nest_cam(dev)
            elif dev.deviceTypeId == "nestGuard":
                self.device_start_comm_nest_guard(dev)
            elif dev.deviceTypeId == "nestDetect":
                self.device_start_comm_nest_detect(dev)
            elif dev.deviceTypeId == "nestLock":
                self.device_start_comm_nest_lock(dev)
            elif dev.deviceTypeId == "nestHomeAwayControl":
                self.device_start_comm_nest_home_away_control(dev)
            elif dev.deviceTypeId == "nestWeather":
                self.device_start_comm_nest_weather(dev)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def device_start_comm_starling_hub(self, dev):
        try:
            if dev.id not in self.globals[HUBS]:
                self.globals[HUBS][dev.id] = dict()
                self.globals[HUBS][dev.id][STARLING_API_VERSION] = ""
                self.globals[HUBS][dev.id][NEST_DEVICES_BY_INDIGO_DEVICE_ID] = dict()
                self.globals[HUBS][dev.id][NEST_DEVICES_BY_NEST_ID] = dict()

            if dev.id not in self.globals[QUEUES]:
                # Create Queues for handling Starling Hub API requests
                self.globals[QUEUES][dev.id] = queue.PriorityQueue()   # Used to queue API requests for specific Starling Hubs
            if dev.id not in self.globals[THREAD]:
                # Create the thread to handle API calls to Starling Hub
                # self.globals[THREAD_STARTED][dev.id] = False
                self.globals[EVENT][dev.id] = threading.Event()
                self.globals[THREAD][dev.id] = Thread_Hub_Handler(self.globals, dev.id, self.globals[EVENT][dev.id])
                self.globals[THREAD][dev.id].start()
                # self.globals[THREAD_STARTED][dev.id] = True

            props = dev.pluginProps
            starling_hub_ip = props.get("starling_hub_ip", "- Unknown -")
            if starling_hub_ip != dev.address:
                props["address"] = starling_hub_ip
                dev.replacePluginPropsOnServer(props)

            keyValueList = [
                {"key": "api_ready", "value": False},
                {"key": "connected_to_nest", "value": False},
                {"key": "status", "value": "Connecting"},
                {"key": "status_message", "value": "Connecting ..."}
            ]
            dev.updateStatesOnServer(keyValueList)
            dev.updateStateImageOnServer(indigo.kStateImageSel.TimerOn)

            self.globals[QUEUES][dev.id].put((QUEUE_PRIORITY_COMMAND_HIGH, API_COMMAND_STATUS, None, None))

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def derive_nest_device_type_Id(self, nest_type):
        try:
            self.logger.error(f"derive_nest_device_type_Id: '{nest_type}'")
            if nest_type == "protect":
                return "nestProtect"
            self.logger.error(f"derive_nest_device_type_Id [2]: '{nest_type}'")
            if nest_type == "thermostat":
                return "nestThermostat"
            # if nest_type == "thermostat":
            #     return "nestTempSensor"
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

    def device_start_comm_nest_protect(self, dev):
        try:
            keyValueList = [
                {"key": "status", "value": "Connecting"},
                {"key": "status_message", "value": "Connecting ..."},
                {"key": "onOffState", "value": False, "uiValue": "Disconnected"}
            ]
            dev.updateStatesOnServer(keyValueList)
            dev.updateStateImageOnServer(indigo.kStateImageSel.TimerOn)

            props = dev.pluginProps
            nest_id = props.get("nest_id", "")
            if nest_id == "":
                self.logger.error(f"Warning: Nest id missing for {dev.name}")
                return
            elif nest_id != dev.address:
                props["address"] = nest_id
                dev.replacePluginPropsOnServer(props)

            hub_id = int(props.get("starling_hub_indigo_id", 0))
            if hub_id == 0:
                self.logger.error(f"Starling Hub id not setup for {dev.name}; Edit the device to specify Starling Hub")
                return
            elif hub_id not in indigo.devices:
                self.logger.error(f"{dev.name} has an assigned Starling Hub that is no longer present in Indigo Devices; Has the Hub been deleted?")
                return

            # Register nest device in NEST_DEVICES_BY_NEST_ID
            #if nest_id not in self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID]:
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id] = dict()
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEV_ID] = dev.id
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEVICE_TYPE_ID] = dev.deviceTypeId
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_NAME] = dev.states["name"]
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_WHERE] = dev.states["where"]

            # Register sub-type devices in NEST_DEVICES_BY_INDIGO_DEVICE_ID
            if dev.id not in self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID]:
                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id] = dict()
                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][NEST_ID] = nest_id

            self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][CO_DEV_ID] = 0
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][MOTION_DEV_ID] = 0

            self.check_grouped_devices(hub_id, dev)  # Check grouped devices and ungroup if necessary

            self.globals[INDIGO_DEVICE_TO_HUB][dev.id] = hub_id

            if hub_id in self.globals[QUEUES]:
                self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_MEDIUM, API_COMMAND_START_DEVICE, [dev.id], None))
            else:
                self.logger.error(f"Warning: Starling Hub queue missing for {dev.name}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def device_start_comm_nest_thermostat(self, dev):
        try:
            keyValueList = [
                {"key": "status", "value": "Connecting"},
                {"key": "status_message", "value": "Connecting ..."},
                {"key": "temperatureInput1", "value": 0, "uiValue": "Disconnected"}
            ]
            dev.updateStatesOnServer(keyValueList)
            dev.updateStateImageOnServer(indigo.kStateImageSel.TimerOn)

            props = dev.pluginProps
            nest_id = props.get("nest_id", "")
            if nest_id == "":
                self.logger.error(f"Warning: Nest id missing for {dev.name}")
                return
            elif nest_id != dev.address:
                props["address"] = nest_id
                dev.replacePluginPropsOnServer(props)

            hub_id = int(props.get("starling_hub_indigo_id", 0))
            if hub_id == 0:
                self.logger.error(f"Starling Hub id not setup for {dev.name}; Edit the device to specify Starling Hub")
                return
            elif hub_id not in indigo.devices:
                self.logger.error(f"{dev.name} has an assigned Starling Hub that is no longer present in Indigo Devices; Has the Hub been deleted?")
                return

            # Register nest device in NEST_DEVICES_BY_NEST_ID
            # if nest_id not in self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID]:
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id] = dict()
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEV_ID] = dev.id
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEVICE_TYPE_ID] = dev.deviceTypeId
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_NAME] = dev.states["name"]
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_WHERE] = dev.states["where"]

            # Register sub-type devices in NEST_DEVICES_BY_INDIGO_DEVICE_ID
            if dev.id not in self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID]:
                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id] = dict()
                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][NEST_ID] = nest_id

            self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][HUMIDIFIER_DEV_ID] = 0
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][FAN_DEV_ID] = 0
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][HOT_WATER_DEV_ID] = 0

            self.check_grouped_devices(hub_id, dev)  # Check grouped devices and ungroup if necessary

            self.globals[INDIGO_DEVICE_TO_HUB][dev.id] = hub_id

            if hub_id in self.globals[QUEUES]:
                self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_MEDIUM, API_COMMAND_START_DEVICE, [dev.id], None))
            else:
                self.logger.error(f"Warning: Starling Hub queue missing for {dev.name}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def device_start_comm_nest_weather(self, dev):
        try:
            keyValueList = [
                {"key": "status", "value": "Connecting"},
                {"key": "status_message", "value": "Connecting ..."},
                {"key": "sensorValue", "value": 0, "uiValue": "Disconnected"}
            ]
            dev.updateStatesOnServer(keyValueList)
            dev.updateStateImageOnServer(indigo.kStateImageSel.TimerOn)

            props = dev.pluginProps
            nest_id = props.get("nest_id", "")
            if nest_id == "":
                self.logger.error(f"Warning: Nest id missing for {dev.name}")
                return
            elif nest_id != dev.address:
                props["address"] = nest_id
                dev.replacePluginPropsOnServer(props)

            hub_id = int(props.get("starling_hub_indigo_id", 0))
            if hub_id == 0:
                self.logger.error(f"Starling Hub id not setup for {dev.name}; Edit the device to specify Starling Hub")
                return
            elif hub_id not in indigo.devices:
                self.logger.error(f"{dev.name} has an assigned Starling Hub that is no longer present in Indigo Devices; Has the Hub been deleted?")
                return

            # Register nest device in NEST_DEVICES_BY_NEST_ID
            # if nest_id not in self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID]:
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id] = dict()
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEV_ID] = dev.id
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEVICE_TYPE_ID] = dev.deviceTypeId
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_NAME] = dev.states["name"]
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_WHERE] = dev.states["where"]

            # Register sub-type devices in NEST_DEVICES_BY_INDIGO_DEVICE_ID
            if dev.id not in self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID]:
                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id] = dict()
                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][NEST_ID] = nest_id

            self.check_grouped_devices(hub_id, dev)  # Check grouped devices and ungroup if necessary

            self.globals[INDIGO_DEVICE_TO_HUB][dev.id] = hub_id

            if hub_id in self.globals[QUEUES]:
                self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_MEDIUM, API_COMMAND_START_DEVICE, [dev.id], None))
            else:
                self.logger.error(f"Warning: Starling Hub queue missing for {dev.name}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def check_grouped_devices(self, hub_id, nest_dev):
        try:
            props = nest_dev.pluginProps
            dev_id_list = indigo.device.getGroupList(nest_dev.id)
            if len(dev_id_list) > 1:
                for linked_dev_id in dev_id_list:
                    if linked_dev_id != nest_dev.id:
                        linked_dev = indigo.devices[linked_dev_id]
                        if nest_dev.deviceTypeId == "nestThermostat":
                            if linked_dev.deviceTypeId == "nestThermostatHumidifier":
                                if props.get("humidifier_enabled", False):
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][HUMIDIFIER_DEV_ID] = linked_dev_id
                                    self.globals[INDIGO_DEVICE_TO_HUB][linked_dev_id] = hub_id
                                else:
                                    # Ungroup linked Humidifier Device
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][HUMIDIFIER_DEV_ID] = 0
                                    self.ungroup_linked_device(nest_dev, linked_dev)
                            elif linked_dev.deviceTypeId == "nestThermostatFan":
                                if props.get("fan_enabled", False):
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][FAN_DEV_ID] = linked_dev_id
                                    self.globals[INDIGO_DEVICE_TO_HUB][linked_dev_id] = hub_id
                                else:
                                    # Ungroup linked Fan Device
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][FAN_DEV_ID] = 0
                                    self.ungroup_linked_device(nest_dev, linked_dev)
                            elif linked_dev.deviceTypeId == "nestThermostatHotWater":
                                if props.get("hot_water_enabled", False):
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][HOT_WATER_DEV_ID] = linked_dev_id
                                    self.globals[INDIGO_DEVICE_TO_HUB][linked_dev_id] = hub_id
                                else:
                                    # Ungroup linked Hot water device
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][HOT_WATER_DEV_ID] = 0
                                    self.ungroup_linked_device(nest_dev, linked_dev)
                        elif nest_dev.deviceTypeId == "nestProtect":
                            if linked_dev.deviceTypeId == "nestProtectCo":
                                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][CO_DEV_ID] = linked_dev_id
                                self.globals[INDIGO_DEVICE_TO_HUB][linked_dev_id] = hub_id
                            elif linked_dev.deviceTypeId == "nestProtectMotion":
                                if props.get("nest_occupancy_detected_enabled", False):
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][MOTION_DEV_ID] = linked_dev_id
                                    self.globals[INDIGO_DEVICE_TO_HUB][linked_dev_id] = hub_id
                                else:
                                    # Ungroup linked Motion Device
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][MOTION_DEV_ID] = 0
                                    self.ungroup_linked_device(nest_dev, linked_dev)
                        elif nest_dev.deviceTypeId == "nestWeather":
                            if linked_dev.deviceTypeId == "nestWeatherHumidity":
                                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][nest_dev.id][HUMIDITY_DEV_ID] = linked_dev_id
                                self.globals[INDIGO_DEVICE_TO_HUB][linked_dev_id] = hub_id


        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def ungroup_linked_device(self, nest_dev, linked_dev):
        try:
            device_type_ui = "Unknown"
            enabled_prop = ""
            if linked_dev.deviceTypeId == "nestThermostatHumidifier":
                device_type_ui = "Humidifier"
                enabled_prop = "humidifier_enabled"
            elif linked_dev.deviceTypeId == "nestThermostatFan":
                device_type_ui = "Fan"
                enabled_prop = "fan_enabled"
            elif linked_dev.deviceTypeId == "nestThermostatHotWater":
                device_type_ui = "Hot Water"
                enabled_prop = "hot_water_enabled"
            elif linked_dev.deviceTypeId == "nestProtectMotion":
                device_type_ui = "Motion"
                enabled_prop = "nest_occupancy_detected_enabled"

            linked_dev_name = linked_dev.name

            indigo.device.ungroupDevice(linked_dev)
            linked_dev.refreshFromServer()
            nest_dev.refreshFromServer()

            props = linked_dev.ownerProps
            props["member_of_device_group"] = False
            linked_dev.replacePluginPropsOnServer(props)

            if enabled_prop != "":
                props = nest_dev.ownerProps
                props[enabled_prop] = False
                nest_dev.replacePluginPropsOnServer(props)

            ungrouped_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ungrouped_name = f"{linked_dev.name} [UNGROUPED @ {ungrouped_time}]"
            linked_dev.name = ungrouped_name
            linked_dev.replaceOnServer()

            self.logger.warning(f"'{device_type_ui}' not enabled for {nest_dev.name}.\n    Device '{linked_dev_name}' ungrouped and renamed to '{ungrouped_name}'")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def device_start_comm_nest_temp_sensor(self, dev):
        try:
            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def device_start_comm_nest_cam(self, dev):
        try:
            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def device_start_comm_nest_guard(self, dev):
        try:
            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def device_start_comm_nest_detect(self, dev):
        try:
            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def device_start_comm_nest_lock(self, dev):
        try:
            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def device_start_comm_nest_home_away_control(self, dev):
        try:
            keyValueList = [
                {"key": "status", "value": "Connecting"},
                {"key": "status_message", "value": "Connecting ..."},
                {"key": "onOffState", "value": False, "uiValue": "Disconnected"}
            ]
            dev.updateStatesOnServer(keyValueList)
            dev.updateStateImageOnServer(indigo.kStateImageSel.TimerOn)

            props = dev.pluginProps
            nest_id = props.get("nest_id", "")
            if nest_id == "":
                self.logger.error(f"Warning: Nest id missing for {dev.name}")
                return
            elif nest_id != dev.address:
                props["address"] = nest_id
                dev.replacePluginPropsOnServer(props)

            hub_id = int(props.get("starling_hub_indigo_id", 0))
            if hub_id == 0:
                self.logger.error(f"Starling Hub id not setup for {dev.name}; Edit the device to specify Starling Hub")
                return
            elif hub_id not in indigo.devices:
                self.logger.error(f"{dev.name} has an assigned Starling Hub that is no longer present in Indigo Devices; Has the Hub been deleted?")
                return

            # Register nest device in NEST_DEVICES_BY_NEST_ID
            # if nest_id not in self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID]:
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id] = dict()
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEV_ID] = dev.id
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEVICE_TYPE_ID] = dev.deviceTypeId
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_NAME] = dev.states["name"]
            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_WHERE] = ""  # Was: dev.states["where"]

            # Register sub-type devices in NEST_DEVICES_BY_INDIGO_DEVICE_ID
            if dev.id not in self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID]:
                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id] = dict()
                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][NEST_ID] = nest_id

            self.globals[INDIGO_DEVICE_TO_HUB][dev.id] = hub_id

            if hub_id in self.globals[QUEUES]:
                self.globals[QUEUES][hub_id].put((QUEUE_PRIORITY_COMMAND_MEDIUM, API_COMMAND_START_DEVICE, [dev.id], None))
            else:
                self.logger.error(f"Warning: Starling Hub queue missing for {dev.name}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def device_stop_comm(self, dev):
        try:
            # self.logger.info(f"Device '{dev.name}' Stopped")

            if dev.deviceTypeId in ("nestProtect", "nestThermostat", "nestHomeAwayControl", "nestWeather"):
                props = dev.pluginProps
                hub_id = props.get("starling_hub_indigo_id", 0)
                if hub_id != 0:
                    if hub_id in self.globals[HUBS]:
                        if dev.id in self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID]:
                            del self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id]
                        nest_id = dev.address  # e.g. "6416660000123456" or possible blank?
                        if nest_id in self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID]:
                            self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEV_ID] = 0
            elif dev.deviceTypeId in ("starlingHub"):
                pass
                # TODO: Stop hubhandler thread

                self.globals[EVENT][dev.id].set()  # Stop the Hub handler Thread
                self.globals[THREAD][dev.id].join(5.0)  # noqa [Expected type 'Iterable[str]', got 'float' instead] - Wait for up t0 5 seconds for it to end

                # Delete thread so that it can be recreated if the Starling Hub device is turned on again
                del self.globals[THREAD][dev.id]
                del self.globals[HUBS][dev.id]

                dev.updateStateOnServer(key='status', value="Disconnected")
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def device_updated(self, origDev, newDev):
        try:
            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        super(Plugin, self).deviceUpdated(origDev, newDev)

    def get_device_config_ui_values(self, plugin_props, type_id="", dev_id=0):
        try:
            if type_id in ("nestProtect", "nestThermostat", "nestHomeAwayControl", "nestWeather"):
                if "starling_hub_indigo_id" not in plugin_props or plugin_props["starling_hub_indigo_id"] == "":
                    plugin_props["starling_hub_indigo_id"] = -1  # -- SELECT --
                if "nest_id" not in plugin_props or plugin_props["nest_id"] == "":
                    plugin_props["nest_id"] = "SELECT"  # -- SELECT --

                starling_hub_indigo_id = int(plugin_props.get("starling_hub_indigo_id", -1))  # -- SELECT --
                if starling_hub_indigo_id != -1 and starling_hub_indigo_id != 0:
                    if starling_hub_indigo_id not in self.globals[HUBS]:
                        plugin_props["starling_hub_indigo_id"] = 0

                if plugin_props["nest_id"] == "SELECT" or plugin_props["nest_id"] == "" or len(plugin_props["nest_id"]) < 4:  # TODO: Check this is reasonable?
                    self.globals[LIST_NEST_DEVICES_SELECTED] = False
                else:
                    self.globals[LIST_NEST_DEVICES_SELECTED] = True

            elif type_id in ("nestProtectMotion", "nestProtectCo", "nestThermostatHumidifier",
                             "nestThermostatFan", "nestThermostatHotWater", "nestWeatherHumidity"):
                # The following code sets the property "member_of_device_group" to True if the secondary device
                #   is associated with a primary device. If not it is set to False. This property is used
                #   in Devices.xml to display a red warning box and disable device editing if set to False.
                plugin_props['member_of_device_group'] = False
                plugin_props["primaryIndigoDevice"] = False
                if dev_id in indigo.devices:
                    dev_id_list = indigo.device.getGroupList(dev_id)
                    if len(dev_id_list) > 1:
                        plugin_props['member_of_device_group'] = True
                        # for linked_dev_id in dev_id_list:
                        #     linked_dev_props = indigo.devices[linked_dev_id].ownerProps
                        #     primary_device = linked_dev_props.get("primaryIndigoDevice", False)
                        #     if primary_device:
                        #         plugin_props['linkedIndigoDeviceId'] = indigo.devices[linked_dev_id].id
                        #         plugin_props['linkedIndigoDevice'] = indigo.devices[linked_dev_id].name
                        #         plugin_props['associatedHubitatDevice'] = linked_dev_props["hubitatDevice"]

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement
        finally:
            return super(Plugin, self).getDeviceConfigUiValues(plugin_props, type_id, dev_id)

    def get_device_state_list(self, nest_dev):
        try:
            state_list = indigo.PluginBase.getDeviceStateList(self, nest_dev)
            if state_list is not None:
                nest_dev_props = nest_dev.pluginProps

                if nest_dev.deviceTypeId == "nestThermostat":

                    # Determine grouped devices

                    # Make sure appropriate dev states are present for the Nest Thermostat
                    if nest_dev_props.get("cooling_enabled", False):
                        target_cooling_threshold_temperature = self.getDeviceStateDictForRealType("target_cooling_threshold_temperature", "Target Cooling Threshold Temperature changed",
                                                                                                  "Target Cooling Threshold Temperature")
                        if target_cooling_threshold_temperature not in state_list:
                            state_list.append(target_cooling_threshold_temperature)
                        target_heating_threshold_temperature = self.getDeviceStateDictForRealType("target_heating_threshold_temperature", "Target Heating Threshold Temperature changed",
                                                                                                  "Target Heating Threshold Temperature")
                        if target_heating_threshold_temperature not in state_list:
                            state_list.append(target_heating_threshold_temperature)

                    if nest_dev_props.get("eco_mode_enabled", False):
                        eco_mode = self.getDeviceStateDictForBoolTrueFalseType("eco_mode", "Eco Mode changed", "Eco Mode")
                        if eco_mode not in state_list:
                            state_list.append(eco_mode)

                    if nest_dev_props.get("fan_enabled", False):
                        fan_running = self.getDeviceStateDictForBoolTrueFalseType("fan_running", "Fan Running changed", "Fan Running")
                        if fan_running not in state_list:
                            state_list.append(fan_running)

                    if nest_dev_props.get("hot_water_enabled", False):
                        hot_water_enabled = self.getDeviceStateDictForBoolTrueFalseType("hot_water_enabled", "Hot Water changed", "Hot Water")
                        if hot_water_enabled not in state_list:
                            state_list.append(hot_water_enabled)

                    # TODO: Implement this if Humidifier data required in main Thermostat device. Currently defined in Humidifier sub-type
                    # if nest_dev_props.get("humidifier_enabled", False):
                    #     current_humidifier_state = self.getDeviceStateDictForStringType("current_humidifier_state", "Current Humidifier State changed", "Current Humidifier State")
                    #     if current_humidifier_state not in state_list:
                    #         state_list.append(current_humidifier_state)
                    #     humidifier_active = self.getDeviceStateDictForBoolTrueFalseType("humidifier_active", "Humidifier Active changed", "Humidifier Active")
                    #     if humidifier_active not in state_list:
                    #         state_list.append(humidifier_active)
                    #     target_humidity = self.getDeviceStateDictForRealType("target_humidity", "Target Humidity changed", "Target Humidity")
                    #     if target_humidity not in state_list:
                    #         state_list.append(target_humidity)

                    if nest_dev_props.get("preset_enabled", False):
                        preset_selected = self.getDeviceStateDictForStringType("preset_selected", "Preset Selected changed", "Preset Selected")
                        if preset_selected not in state_list:
                            state_list.append(preset_selected)

                    if nest_dev_props.get("sensor_enabled", False):
                        sensor_selected = self.getDeviceStateDictForStringType("sensor_selected", "Sensor Selected changed", "Sensor Selected")
                        if sensor_selected not in state_list:
                            state_list.append(sensor_selected)

                    if nest_dev_props.get("temp_hold_mode_enabled", False):
                        temp_hold_mode = self.getDeviceStateDictForBoolTrueFalseType("temp_hold_mode", "Temp Hold Mode changed", "Temp Hold Mode")
                        if temp_hold_mode not in state_list:
                            state_list.append(temp_hold_mode)

            # self.logger.error(f"'{nest_dev.name}' States: {state_list}")  # Debug Assist

            return state_list

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def get_prefs_config_ui_values(self):
        prefs_config_ui_values = self.pluginPrefs
        try:
            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        return prefs_config_ui_values

    def run_concurrent_thread(self):
        try:
            self.sleep(10)
            while True:
                # self.logger.warning(f"Starling runConcurrentThread looping every {self.globals[POLLING_SECONDS]} second(s).")
                nest_device_list = list()
                for starling_hub_dev_id in self.globals[HUBS]:
                    if starling_hub_dev_id in self.globals[QUEUES]:
                        for nest_id in self.globals[HUBS][starling_hub_dev_id][NEST_DEVICES_BY_NEST_ID]:
                            nest_dev_id = self.globals[HUBS][starling_hub_dev_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEV_ID]
                            if nest_dev_id != 0:
                                nest_device_list.append(nest_dev_id)
                        if len(nest_device_list) > 0:
                            self.globals[QUEUES][starling_hub_dev_id].put((QUEUE_PRIORITY_POLLING, API_COMMAND_POLL_DEVICE, nest_device_list, None))
                self.sleep(self.globals[POLLING_SECONDS])

        except self.StopThread:
            # if needed, you could do any cleanup here, or could exit via another flag
            # or command from your plugin
            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        # self.logger.warning("Starling runConcurrentThread SHUTDOWN")

    def shutdown(self):
        try:
            pass
            # self.logger.warning("Starling SHUTDOWN")
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def startup(self):
        try:
            # self.debug = False

            # First list and process all Starling Hubs
            for dev in indigo.devices.iter("self"):
                if dev.deviceTypeId == "starlingHub":
                    if dev.enabled:
                        # props = dev.pluginProps
                        self.globals[HUBS][dev.id] = dict()
                        self.globals[HUBS][dev.id][NEST_DEVICES_BY_INDIGO_DEVICE_ID] = dict()
                        self.globals[HUBS][dev.id][NEST_DEVICES_BY_NEST_ID] = dict()

                        # Create Queues for handling Starling Hub API requests
                        self.globals[QUEUES][dev.id] = queue.PriorityQueue()  # Used to queue API requests for specific Starling Hubs

            # Secondly, then process all Starling Nest devices
            for dev in indigo.devices.iter("self"):
                if dev.deviceTypeId in ("nestProtect", "nestThermostat", "nestHomeAwayControl", "nestWeather"):  # TODO: More to be added - 30-Mar-2022
                    if dev.enabled:
                        props = dev.pluginProps
                        hub_id = int(props.get("starling_hub_indigo_id", 0))
                        if hub_id != 0:
                            if hub_id in self.globals[HUBS]:
                                nest_id = dev.address  # e.g. "6416660000123456"
                                nest_name = dev.states["name"]  # i.e. Name of the device, e.g. "Thermostat", if set in the Nest app (otherwise, "").
#                                                                               HomeKit accessory names are formed by appending the "name" property to the "where" property
                                if dev.deviceTypeId == "nestHomeAwayControl":
                                    nest_where = ""
                                else:
                                    nest_where = dev.states["where"]  # i.e. Location of device, e.g. "Front Room", if set in the Nest app (otherwise, "")
                                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id] = dict()
                                self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][NEST_ID] = nest_id

                                # Initialise device ids of sub-type devices
                                if dev.deviceTypeId == "nestThermostat":
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][HUMIDIFIER_DEV_ID] = 0
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][FAN_DEV_ID] = 0
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][HOT_WATER_DEV_ID] = 0
                                elif dev.deviceTypeId == "nestProtect":
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][CO_DEV_ID] = 0
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][MOTION_DEV_ID] = 0
                                elif dev.deviceTypeId == "nestWeather":
                                    self.globals[HUBS][hub_id][NEST_DEVICES_BY_INDIGO_DEVICE_ID][dev.id][HUMIDITY_DEV_ID] = 0

                                self.check_grouped_devices(hub_id, dev)
                                
                                self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id] = dict()
                                self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEV_ID] = dev.id
                                self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEVICE_TYPE_ID] = dev.deviceTypeId
                                self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_NAME] = nest_name
                                self.globals[HUBS][hub_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_WHERE] = nest_where

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def stop_concurrent_thread(self):
        try:
            # self.logger.info("Starling plugin closing down")
            for starling_hub_dev_id in self.globals[HUBS]:
                self.globals[QUEUES][starling_hub_dev_id].put((QUEUE_PRIORITY_STOP_THREAD, STOP_THREAD, None, None))
            self.stopThread = True
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def validate_action_config_ui(self, values_dict, type_id, action_id):  # noqa [parameter value is not used]
        try:
            error_dict = indigo.Dict()

            return True, values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def validate_device_config_ui(self, values_dict=None, type_id="", dev_id=0):
        try:
            error_dict = indigo.Dict()

            if type_id == "starlingHub":
                pass

            elif type_id in ("nestProtect", "nestThermostat", "nestHomeAwayControl", "nestWeather"):
                if values_dict["starling_hub_indigo_id"] in (-2,-1,0):
                    error_message = "Starling Hub is not valid. Select a Starling Hub or Cancel"
                    error_dict["starling_hub_indigo_id"] = error_message
                    error_dict["showAlertText"] = error_message
                    return False, values_dict, error_dict

                if values_dict["nest_id"] in ("", "SELECT_HUB", "NO_HUB", "SELECT_NEST", "NO_NESTS"):
                    error_message = "Nest Id is not valid. Select a Nest device or Cancel"
                    error_dict["nest_id"] = error_message
                    error_dict["showAlertText"] = error_message
                    return False, values_dict, error_dict
                if type_id == "nestProtect":
                    values_dict["SupportsBatteryLevel"] = True
                    values_dict["SupportsOnState"] = True
                    values_dict["AllowOnStateChange"] = True
                    values_dict["SupportsStatusRequest"] = False
                    values_dict["SupportsSensorValue"] = False
                    values_dict["AllowSensorValueChange"] = False
                elif type_id == "nestThermostat":
                    values_dict["SupportsBatteryLevel"] = False
                    values_dict["NumHumidityInputs"] = 1
                    values_dict["NumTemperatureInputs"] = 1
                    values_dict["ShowCoolHeatEquipmentStateUI"] = True
                    values_dict["SupportsCoolSetpoint"] = False
                    values_dict["SupportsHeatSetpoint"] = True
                    values_dict["SupportsHvacFanMode"] = False
                    values_dict["SupportsHvacOperationMode"] = True
                    values_dict["SupportsOnState"] = False
                    values_dict["SupportsSensorValue"] = True
                    values_dict["SupportsStatusRequest"] = False
                    values_dict["supportsTemperatureReporting"] = True
                elif type_id == "nestHomeAwayControl":
                    pass
                elif type_id == "nestWeather":
                    values_dict["SupportsBatteryLevel"] = False
                    values_dict["SupportsOnState"] = False
                    # values_dict["NumHumidityInputs"] = 1
                    values_dict["NumTemperatureInputs"] = 1
                    values_dict["SupportsSensorValue"] = True
                    values_dict["SupportsStatusRequest"] = True
                    values_dict["supportsTemperatureReporting"] = True
            else:
                # Assume a Secondary Device
                if not values_dict.get("member_of_device_group", False):
                    error_message = "You aren't allowed to Create and Save an ungrouped secondary device. Cancel and delete device."
                    error_dict["warning"] = error_message
                    error_dict["showAlertText"] = error_message
                    return False, values_dict, error_dict

            return True, values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def validate_prefs_config_ui(self, values_dict): # noqa [Method is not declared static]
        try:
            # self.logger.info(f"FILTERABLE_DEVICES [JSON_DUMPS]: {self.globals[FILTERABLE_DEVICES]}")
            filterable_devices_json = json.dumps(self.globals[FILTERABLE_DEVICES])
            values_dict["filterable_devices"] = filterable_devices_json

            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        return True, values_dict

    #################################
    #
    # Start of bespoke plugin methods
    #
    #################################

    def refresh_ui_callback(self, valuesDict, typeId="", devId=None):  # noqa [parameter value is not used]
        errors_dict = indigo.Dict()
        try:
            # self.logger.info(f"LIST_NEST_DEVICES_SELECTED: {self.globals[LIST_NEST_DEVICES_SELECTED]}")
            if typeId == "starlingHub":
                return valuesDict, errors_dict

            try:
                starling_hub_indigo_id = int(valuesDict.get("starling_hub_indigo_id", -1))  # -- SELECT --
                if len(self.globals[LIST_STARLING_HUBS]) == 0:
                    valuesDict["starling_hub_indigo_id"] = 0
                elif len(self.globals[LIST_STARLING_HUBS]) == 1:
                    for starling_hub_indigo_id in self.globals[LIST_STARLING_HUBS]:
                        break
                    valuesDict["starling_hub_indigo_id"] = starling_hub_indigo_id
            except ValueError:
                starling_hub_indigo_id = -1

            try:
                nest_id = valuesDict.get("nest_id", "NO_NESTS")  # -- SELECT --
            except ValueError:
                nest_id = "NO_NESTS"

            if starling_hub_indigo_id == -1:  # -- SELECT --
                valuesDict["nest_id"] = "SELECT_HUB"  # -- FIRST SELECT --  # TODO: Check how to handle -1 [-SELECT-] for Nest device - 30-Mar-22
            elif starling_hub_indigo_id == 0:  # -- NONE --
                valuesDict["nest_id"] = "NO_HUB"  # -- NONE --
            elif len(self.globals[LIST_NEST_DEVICES]) == 0:
                valuesDict["nest_id"] = "NO_NESTS"
            # elif len(self.globals[LIST_NEST_DEVICES]) == 1:
            #     for nest_id in self.globals[LIST_NEST_DEVICES]:
            #         break
            #     valuesDict["nest_id"] = nest_id
            # else:
            elif not self.globals[LIST_NEST_DEVICES_SELECTED]:
                valuesDict["nest_id"] = "SELECT_NEST"

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        return valuesDict, errors_dict

    def list_starling_hubs(self, filter="", valuesDict=None, typeId="", targetId=0):  # noqa [parameter value is not used]
        try:
            starling_hubs_list = list()
            for dev in indigo.devices.iter("self"):
                if dev.deviceTypeId == "starlingHub":
                    starling_hubs_list.append((dev.id, dev.name))
                    self.globals[LIST_STARLING_HUBS].add(dev.id)

            if len(starling_hubs_list) == 0:
                starling_hubs_list = list()
                starling_hubs_list.append((0, "-- NO STARLING HUBS AVAILABLE --"))
                return starling_hubs_list

            if len(starling_hubs_list) > 1:
                starling_hubs_list.append((-1, "-- SELECT STARLING HUB --"))

            # print(f"LIST_STARLING_HUBS: {starling_hubs_list}")
            return sorted(starling_hubs_list, key=lambda name: name[1].lower())   # sort by starling hub name

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def list_starling_hub_selected(self, valuesDict, typeId, devId):  # noqa [parameter value is not used]
        try:
            # do whatever you need to here
            #   typeId is the device type specified in the Devices.xml
            #   devId is the device ID - 0 if it's a new device
            self.globals[LIST_NEST_DEVICES_SELECTED] = False
            self.logger.debug(f"Starling Hub Selected: {valuesDict['starling_hub_indigo_id']}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        return valuesDict

    def list_nest_devices(self, filter="", valuesDict=None, typeId="", targetId=0):  # noqa [parameter value is not used]
        try:
            # self.globals[LIST_NEST_DEVICES_SELECTED] = False
            # self.logger.info(f"LIST_NEST_DEVICES_SELECTED [1]: {self.globals[LIST_NEST_DEVICES_SELECTED]}")

            nest_devices_list = list()

            starling_hub_indigo_id = int(valuesDict.get("starling_hub_indigo_id", -1))  # -- SELECT --
            if starling_hub_indigo_id == -1:
                nest_devices_list.append(("SELECT_HUB", "^^^ Select Starling Hub First ^^^"))
                return nest_devices_list
            elif starling_hub_indigo_id == 0:
                nest_devices_list.append(("NO_HUB", "^^^ No Starling Hub available ^^^"))
                return nest_devices_list

            # build list of Indigo devices already allocated to Starling Nest devices of the required type
            allocated_devices = dict()
            for dev in indigo.devices.iter("self"):
                if dev.id != targetId and dev.deviceTypeId == typeId:
                    nest_id = dev.address
                    allocated_devices[nest_id] = dev.id

            nest_devices_list = list()
            self.globals[LIST_NEST_DEVICES].clear()

            if starling_hub_indigo_id > 0 and starling_hub_indigo_id in indigo.devices:
                for nest_id in self.globals[HUBS][starling_hub_indigo_id][NEST_DEVICES_BY_NEST_ID].keys():
                    if typeId != self.globals[HUBS][starling_hub_indigo_id][NEST_DEVICES_BY_NEST_ID][nest_id][INDIGO_DEVICE_TYPE_ID]:
                        continue  # Continue to check next nest id as not required device type
                    if nest_id in allocated_devices:
                        continue  # Continue as already allocated to another Indigo Nest device

                    nest_where = self.globals[HUBS][starling_hub_indigo_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_WHERE]
                    nest_name = self.globals[HUBS][starling_hub_indigo_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_NAME]

                    if nest_where == "":
                        nest_list_entry = f"{nest_name}"
                    else:
                        nest_list_entry = f"{nest_name} [{nest_where}]"

                    nest_devices_list.append((nest_id, nest_list_entry))
                    self.globals[LIST_NEST_DEVICES].add(nest_id)

            if len(nest_devices_list) > 0:
                nest_devices_list.append(("SELECT_NEST", "-- SELECT NEST DEVICE --"))
                # self.logger.info(f"LIST_NEST_DEVICES_SELECTED [2A]: {self.globals[LIST_NEST_DEVICES_SELECTED]}")
                return sorted(nest_devices_list, key=lambda name: name[1].lower())   # sort by starling device name
            else:  # List empty
                nest_devices_list.append(("NO_NESTS", f"No \"{typeId}\" devices available"))
            # self.logger.info(f"LIST_NEST_DEVICES_SELECTED [2B]: {self.globals[LIST_NEST_DEVICES_SELECTED]}")
            return nest_devices_list

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def list_nest_device_selected(self, valuesDict, typeId, devId):  # noqa [parameter value is not used]
        try:
            starling_hub_indigo_id = int(valuesDict.get("starling_hub_indigo_id", 0))
            nest_id = valuesDict["nest_id"]
            if starling_hub_indigo_id > 0:
                if nest_id not in ("", "SELECT_HUB", "NO_HUB", "SELECT_NEST", "NO_NESTS"):
                    valuesDict["nest_where"] = self.globals[HUBS][starling_hub_indigo_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_WHERE]
                    valuesDict["nest_name"] = self.globals[HUBS][starling_hub_indigo_id][NEST_DEVICES_BY_NEST_ID][nest_id][NEST_NAME]
                    self.globals[LIST_NEST_DEVICES_SELECTED] = True
                    # self.logger.info(f"LIST_NEST_DEVICES_SELECTED [3]: {self.globals[LIST_NEST_DEVICES_SELECTED]}")

            pass
            # TODO: Check this - 30-Mar-22 = self.logger.debug(f"Starling Hub Selected: {valuesDict['starlingHubId']}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        return valuesDict

    def access_starling_hub(self, starling_hub_dev, starling_command):
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
                requests_prefix = (f"https://{https_ip_1}-{https_ip_2}-{https_ip_3}-{https_ip_4}.local.starling.direct:3443/api/connect/v1/")
            else:
                requests_prefix = f"http://{ip_address}:3443/api/connect/v1/"  # noqa [http links are not secure]
            api_key = props.get("api_key", "not_set_in_plugin")
            requests_suffix = f"?key={api_key}"
            requests_string = f"{requests_prefix}{starling_command}{requests_suffix}"

            print(f"access_starling_hub Request String: {requests_string}")

            error_code = None
            error_message = None

            try:
                reply = requests.get(requests_string, timeout=5)
                # print(f"Reply Status: {reply.status_code}, Text: {reply.text}")
                status_code = reply.status_code
                if status_code == 200:
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
                self.logger.error(f"Error [{status_code}] accessing Starling Hub '{starling_hub_dev.name}': {error_code}\n{error_message}")
                return status, [error_code, error_message]

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

