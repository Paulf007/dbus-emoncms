#!/usr/bin/python -u

# Script Created by Paul F Prinsloo to upload Victron Data to EmonCMS via the Venus OS / Color control 


import sys, os, time, sys, string
import logging
from functools import partial
from collections import Mapping
from datetime import datetime
import dbus
from dbus.mainloop.glib import DBusGMainLoop
import gobject
import requests
import httplib
import urllib
import json
import urllib2


#Setup For EmonCMS
#-----------------------------------------------------------------------------------------------------#
# Domain you want to post to: localhost would be an emoncms installation on your own laptop
# this could be changed to emoncms.org to post to emoncms.org or your own server
server = "198.46.196.157"


# Location of emoncms in your server, the standard setup is to place it in a folder called emoncms
# To post to emoncms.org change this to blank: ""
emoncmspath = "emoncms"

# ------------- Write apikey of emoncms account -------------
apikey = "d1118332eb96a799779b4f922c1ac986"

# ------------- Node id youd like the emontx to appear as -------------
nodeid = 1

# ------------- Interval to upload data in Ms -------------
INTERVAL = 30000


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def find_services(bus, tp):
    return [str(service) for service in bus.list_names() \
        if service.startswith('com.victronenergy.{}'.format(tp))]

class smart_dict(dict):
    """ Dictionary that can be accessed via attributes. """
    def __getattr__(self, k):
        try:
            v = self[k]
            if isinstance(v, Mapping):
                return self.__class__(v)
            return v
        except KeyError:
            raise AttributeError(k)
    def __setattr__(self, k, v):
        self[k] = v

dbus_int_types = (dbus.Int32, dbus.UInt32, dbus.Byte, dbus.Int16, dbus.UInt16,
        dbus.UInt32, dbus.Int64, dbus.UInt64)

def unwrap_dbus_value(val):
    """Converts D-Bus values back to the original type. For example if val is
       of type DBus.Double, a float will be returned."""
    if isinstance(val, dbus_int_types):
        return int(val)
    if isinstance(val, dbus.Double):
        return float(val)
    return None

def set_state(state, key, v):
    state[key] = value = unwrap_dbus_value(v["Value"])

def query(conn, service, path):
    return conn.call_blocking(service, path, None, "GetValue", '', [])

def track(conn, state, service, path, target):
    # Initialise state
    state[target] = value = unwrap_dbus_value(query(conn, service, path))

    # And track it
    conn.add_signal_receiver(partial(set_state, state, target),
            dbus_interface='com.victronenergy.BusItem',
            signal_name='PropertiesChanged',
            path=path,
            bus_name=service)

def main():
    logging.basicConfig(level=logging.INFO)

    DBusGMainLoop(set_as_default=True)
    conn = dbus.SystemBus()

    generators = smart_dict()
    consumers = smart_dict()
    stats = smart_dict()

    # -------------   Set the user timezone -------------
    if 'TZ' not in os.environ:
        tz = query(conn, "com.victronenergy.settings", "/Settings/System/TimeZone")
        if tz is not None:
            os.environ['TZ'] = tz

    # -------------   Find solarcharger services -------------
    solarchargers = find_services(conn, 'solarcharger')
    logger.info("Found solarchargers at %s", ', '.join(solarchargers))
    
    # -------------   Find grid meters -------------
    meters = find_services(conn, 'grid')
    logger.info("Found grid meters at %s", ', '.join(meters))

    # -------------   Find vebus service ----------------------
    vebus = str(query(conn, "com.victronenergy.system", "/VebusService"))
    logger.info("Found vebus at %s", vebus)

    # -------------   Track solarcharger yield ----------------------
    for charger in solarchargers:
        track(conn, stats, charger, "/Yield/User", "charger")
        track(conn, stats, charger, "/Pv/I", "pva")
        track(conn, stats, charger, "/Pv/V", "pvv")


    # -------------  Track vebus consumption, from battery to input and output ----------------------
    track(conn, stats, vebus, "/Energy/InverterToAcOut", "c1")
    track(conn, stats, vebus, "/Energy/InverterToAcIn1", "c2")
   
    # -------------  track grid info ------------------------------
    track(conn, stats, vebus, "/Ac/ActiveIn/L1/F", "vebf")
    track(conn, stats, vebus, "/Ac/ActiveIn/L1/I", "grid_current")
    track(conn, stats, vebus, "/Ac/ActiveIn/L1/P", "grid_power")
    track(conn, stats, vebus, "/Ac/ActiveIn/L1/V", "grid_volts")

    # -------------  track main load info -------------------------
    track(conn, stats, vebus, "/Ac/Out/L1/F", "load_hz")
    track(conn, stats, vebus, "/Ac/Out/L1/I", "load_current")
    track(conn, stats, vebus, "/Ac/Out/L1/P", "load_power")
    track(conn, stats, vebus, "/Ac/Out/L1/S", "load_s")
    track(conn, stats, vebus, "/Ac/Out/L1/V", "load_volts")

 
    # ------------- Track power values --------------------------
    track(conn, stats, "com.victronenergy.system", "/Ac/Consumption/L1/Power", "pc")
    track(conn, stats, "com.victronenergy.system", "/Ac/Grid/L1/Power", "gridload")
    track(conn, stats, "com.victronenergy.system", "/Dc/Battery/ConsumedAmphours", "cah")
    track(conn, stats, "com.victronenergy.system", "/Dc/Battery/Current", "battery_Current")
    track(conn, stats, "com.victronenergy.system", "/Dc/Battery/Power", "battery_power")
    track(conn, stats, "com.victronenergy.system", "/Dc/Battery/Soc", "battery_soc")

    track(conn, stats, "com.victronenergy.system", "/Dc/Pv/Power", "pg")
    track(conn, stats, "com.victronenergy.system", "/Dc/Pv/Power", "pg")
    track(conn, stats, "com.victronenergy.system", "/Dc/Battery/Voltage", "v6")
    

    # ------------------- Periodic work ---------------------
    def _upload():

        now = datetime.now()

        # ----------------------------------------------- setup data for upload ----------------------------------------------------------------- #
        # -------------  battery info ----------------------
        payload ="batt_volts:"+str(stats.v6)
        payload +=",battery_Current:"+str(stats.battery_Current)
        payload +=",battery_ConsumedAmpHours:"+str(stats.cah)
        payload +=",battery_power:"+str(stats.battery_power)
        payload +=",battery_soc:"+str(stats.battery_soc)
        payload +=",battery_InverterToAcOut:"+str(stats.c1)
        payload +=",battery_InverterToAcIn1:"+str(stats.c2)

        # -------------  solar info ----------------------
        payload +=",solar_watts:"+str(stats.pg)
        payload +=",solar_amps:"+str(stats.pva)
        payload +=",solar_volts:"+str(stats.pvv)
        payload +=",solar_generated:"+str(stats.charger)
        
        # ------------- main load info ----------------------
        payload +=",house_load:"+str(stats.pc)
	payload +=",load_hz:"+str(stats.load_hz)
	payload +=",load_current:"+str(stats.load_current)
	payload +=",load_power:"+str(stats.load_power)
	payload +=",load_volts:"+str(stats.load_volts)
	payload +=",load_s:"+str(stats.load_s)


        # ------------- grid info ----------------------
        payload +=",grid_feed:"+str(stats.gridload)
	payload +=",grid_hz:"+str(stats.vebf)
	payload +=",grid_current:"+str(stats.grid_current)
	payload +=",grid_power:"+str(stats.grid_power)
	payload +=",grid_volts:"+str(stats.grid_volts)

        # --------------------------------------------- upload data to emon --------------------------------------------------------------- #   
        try:
            conn = httplib.HTTPConnection(server)
            conn.request("GET", "/"+emoncmspath+"/input/post.json?&node="+str(nodeid)+"&json="+"{"+payload+"}"+"&apikey="+apikey)
            response = conn.getresponse()
            conn.close()
            print "Emondata sent:" + payload
        except Exception as e:
            print "error sending to emoncms...: " + str(e)
            return [0]
        return [1]        
	# ---------------------------------------------------------------------------------------------------------------- #   


    _upload()
    gobject.timeout_add(INTERVAL, _upload)

    gobject.MainLoop().run()


if __name__ == "__main__":
    main()
