/**
 * tab-settings.js — Settings/Model Info tab (wraps tab-model.js)
 *
 * Delegates to existing App.tabs.model.load()
 */
(function () {
    "use strict";

    function load() {
        if (App.tabs.model && App.tabs.model.load) {
            App.tabs.model.load();
        }
    }

    App.tabs.settings = { load };
})();
