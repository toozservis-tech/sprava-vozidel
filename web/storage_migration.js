/**
 * localStorage key migration (Správa vozidel – fáze 2).
 * Prefer sprava_vozidel_*; read legacy toozhub_* as fallback; copy to new on read; write removes legacy.
 * @deprecated Legacy keys removed in a future phase 3.
 */
(function (global) {
    'use strict';

    var KEYS = {
        apiUrl: { primary: 'sprava_vozidel_api_url', legacy: 'toozhub_api_url' },
        vehicleViewMode: { primary: 'sprava_vozidel_vehicle_view_mode', legacy: 'toozhub_vehicle_view_mode' },
        reminderViewMode: { primary: 'sprava_vozidel_reminder_view_mode', legacy: 'toozhub_reminder_view_mode' },
        reminderFilterMode: { primary: 'sprava_vozidel_reminder_filter_mode', legacy: 'toozhub_reminder_filter_mode' },
        reminderCalendarMonth: { primary: 'sprava_vozidel_reminder_calendar_month', legacy: 'toozhub_reminder_calendar_month' },
        reminderNotificationCheckAt: { primary: 'sprava_vozidel_reminder_notification_check_at', legacy: 'toozhub_reminder_notification_check_at' },
    };

    function readWithMigrate(store, def) {
        try {
            var p = store.getItem(def.primary);
            if (p != null && p !== '') {
                return p;
            }
            var leg = store.getItem(def.legacy);
            if (leg != null && leg !== '') {
                try {
                    store.setItem(def.primary, leg);
                } catch (e1) { /* ignore quota */ }
                return leg;
            }
        } catch (e) { /* ignore */ }
        return null;
    }

    function writeLocal(def, value) {
        try {
            global.localStorage.setItem(def.primary, value);
        } catch (e1) { /* ignore */ }
        try {
            global.localStorage.removeItem(def.legacy);
        } catch (e2) { /* ignore */ }
    }

    function removeLocal(def) {
        try {
            global.localStorage.removeItem(def.primary);
        } catch (e1) { /* ignore */ }
        try {
            global.localStorage.removeItem(def.legacy);
        } catch (e2) { /* ignore */ }
    }

    global.SpravaVozidelStorageKeys = KEYS;
    global.SpravaVozidelStorage = {
        /** @param {keyof typeof KEYS} name */
        getLocal: function (name) {
            return readWithMigrate(global.localStorage, KEYS[name]);
        },
        /** @param {keyof typeof KEYS} name */
        setLocal: function (name, value) {
            writeLocal(KEYS[name], value);
        },
        /** @param {keyof typeof KEYS} name */
        removeLocal: function (name) {
            removeLocal(KEYS[name]);
        },
    };
}(typeof window !== 'undefined' ? window : globalThis));
