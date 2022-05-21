"""Platform for light integration."""
from __future__ import annotations

import logging

import voluptuous as vol
import asyncio

# Import the device class from the component that you want to support
import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    PLATFORM_SCHEMA,
    LightEntity,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR_TEMP,
    SUPPORT_COLOR)
from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    CONF_TOKEN,
    ATTR_ENTITY_ID,
    CONF_SCAN_INTERVAL
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.event import async_track_time_interval

from miio import Device, DeviceException
from math import ceil, floor
from datetime import timedelta

DOMAIN = "xiaomi_miio_opple_light"
DATA_KEY = 'light.xiaomi_miio_opple_light'

MIN_SCAN_INTERVAL = timedelta(seconds=5)
DEFAULT_SCAN_INTERVAL = timedelta(seconds=10)

CONF_MIN_BRIGHTNESS = 'min_brightness'
CONF_MAX_BRIGHTNESS = 'max_brightness'
CONF_MIN_COLOR_TEMPERATURE = 'min_color_temperature'
CONF_MAX_COLOR_TEMPERATURE = 'max_color_temperature'

DEFAULT_SUPPORTED_FEATURES = SUPPORT_BRIGHTNESS | SUPPORT_COLOR_TEMP

_LOGGER = logging.getLogger(__name__)

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_TOKEN): cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL):
        vol.All(cv.time_period, vol.Clamp(min=MIN_SCAN_INTERVAL)),
    vol.Optional(CONF_MIN_BRIGHTNESS, default=7): cv.positive_int,
    vol.Optional(CONF_MAX_BRIGHTNESS, default=100): cv.positive_int,
    vol.Optional(CONF_MIN_COLOR_TEMPERATURE, default=3000): cv.positive_int,
    vol.Optional(CONF_MAX_COLOR_TEMPERATURE, default=5700): cv.positive_int
})

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}

    name = config.get(CONF_NAME)
    host = config.get(CONF_HOST)
    token = config.get(CONF_TOKEN)
    scan_interval = config.get(CONF_SCAN_INTERVAL)
    
    min_brightness = config.get(CONF_MIN_BRIGHTNESS)
    max_brightness = config.get(CONF_MAX_BRIGHTNESS)
    min_color_temperature = config.get(CONF_MIN_COLOR_TEMPERATURE)
    max_color_temperature = config.get(CONF_MAX_COLOR_TEMPERATURE)
    
    hub = OppleLight(hass, name, host, token, scan_interval, min_brightness, max_brightness, min_color_temperature, max_color_temperature)
    hass.data[DATA_KEY][host] = hub
    async_add_entities([hub], update_before_add=True)
    

class OppleLight(LightEntity):

    def __init__(
        self, 
        hass: HomeAssistant,
        name: str, 
        host: str, 
        token: str, 
        scan_interval: int,
        min_brightness: int, 
        max_brightness: int, 
        min_color_temperature: int, 
        max_color_temperature: int
    ) -> None:
        self.hass = hass
        self._name = name

        try:
            self._device = Device(host, token)
            device_info = self._device.info()
            self._unique_id = "{}-{}".format(device_info.model, device_info.mac_address)
            _LOGGER.info(
                "%s %s detected",
                device_info.firmware_version,
                device_info.hardware_version,
            )
        except DeviceException as ex:
            _LOGGER.error("Device unavailable or token incorrect: %s", ex)
            raise PlatformNotReady

        self._scan_interval = scan_interval
        self._remove_update_interval = None
        self._should_poll = False
        
        self._state = None
        self._brightness = None
        self._color_temp = None
        
        self._min_brightness = min_brightness
        self._max_brightness = max_brightness
        self._min_color_temperature = min_color_temperature
        self._max_color_temperature = max_color_temperature
        
    async def async_added_to_hass(self) -> None:
        """Start custom polling."""
        self._remove_update_interval = async_track_time_interval(
            self.hass, self.async_schedule_update, self._scan_interval
        )

    async def async_will_remove_from_hass(self) -> None:
        """Stop custom polling."""
        self._remove_update_interval()

    @callback
    async def async_schedule_update(self, event_time=None):
        """Update the entity."""
        await self.async_update()
        self.async_schedule_update_ha_state()

    async def async_update(self) -> None:
        try:
            BaseInfo = self._device.raw_command('SyncBaseInfo', [])
            self._state = BaseInfo[0]
            self._brightness = BaseInfo[2]
            self._color_temp = BaseInfo[1]
            _LOGGER.debug('Sync_state. Result: %s', str(BaseInfo))
        except Exception:
            _LOGGER.error('Update state error.', exc_info=True)
            
    async def change_state(self, method: str, params: tuple) -> bool | None:
        try:
            res = self._device.raw_command(method, params)
            _LOGGER.debug('Change_state for %s: %s. Result: %s', method, str(params), str(res))
            if (res[0] != 'ok'):
                _LOGGER.error('Change_state failed for %s: %s', method, str(params))
                return False
            else:
                return True
        except Exception:
            _LOGGER.error('Change_state error.', exc_info=True)
            
    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self._state:
            result = await self.change_state("SetState", [True])
            if result:
                self._state = True
        
        if self.supported_features & SUPPORT_BRIGHTNESS and ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            percent_brightness = ceil( (brightness - 1)*(self._max_brightness - self._min_brightness)/(255-1)+self._min_brightness )
            _LOGGER.debug('Setting brightness: %s %s%%', brightness, percent_brightness)
            result = await self.change_state('SetBrightness', [percent_brightness])
            if result:
                self._brightness = brightness
                
        if self.supported_features & SUPPORT_COLOR_TEMP and ATTR_COLOR_TEMP in kwargs:
            mired = kwargs[ATTR_COLOR_TEMP]
            color_temp = self.translate_mired(mired)
            _LOGGER.debug('Setting color temperature: %s mireds, %s ct', mired, color_temp)
            result = await self.change_state('SetColorTemperature', [color_temp])
            if result:
                self._color_temp = color_temp
        
        self.async_schedule_update_ha_state()
                
    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._state:
            result = await self.change_state("SetState", [False])
            if result:
                self._state = False
                
        self.async_schedule_update_ha_state()

    @property
    def name(self) -> str:
        """Return the display name of this light."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return an unique ID."""
        return self._unique_id
        
    @property
    def supported_features(self) -> int:
        return DEFAULT_SUPPORTED_FEATURES
        
    @property
    def should_poll(self) -> bool | None:
        return self._should_poll

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._state

    @property
    def brightness(self) -> int:
        return ceil( (self._brightness - self._min_brightness)*(255-1)/(self._max_brightness - self._min_brightness)+1 )

    @property
    def color_temp(self) -> int:
        return self.translate_mired(self._color_temp)
        
    @property
    def min_mireds(self) -> int:
        return self.translate_mired(self._max_color_temperature)

    @property
    def max_mireds(self) -> int:
        return self.translate_mired(self._min_color_temperature)

    @staticmethod
    def translate_mired(num) -> int:
        try:
            return floor(1000000 / num)
        except (TypeError, ValueError, ZeroDivisionError):
            return 153
