/**
 * BigCertificados WebPKI Bridge
 *
 * Some e-SAJ pages (petitioning, etc.) use the Lacuna Web PKI JavaScript
 * library which looks for the Lacuna extension ID, not the Softplan Web
 * Signer ID. This bridge:
 *
 * 1. Injects the Lacuna meta tag so the library detects "extension installed"
 * 2. Relays messages between Lacuna event names ↔ Softplan event names
 *    so the Web Signer extension handles requests from the Lacuna library
 */

(function () {
  'use strict';

  // ── Lacuna Web PKI IDs and event names ──
  var LACUNA_META_IDS = [
    'webpki_lacunasoftware_com',
    'hcfbhicnnpfhfajegpphblnbjkoimfog'
  ];
  var LACUNA_REQUEST = 'com.lacunasoftware.WebPKI.RequestEvent';
  var LACUNA_RESPONSE = 'com.lacunasoftware.WebPKI.ResponseEvent';

  // ── Softplan Web Signer event names ──
  var SOFTPLAN_REQUEST = 'br.com.softplan.WebPKI.RequestEvent';
  var SOFTPLAN_RESPONSE = 'br.com.softplan.WebPKI.ResponseEvent';

  // ── 1. Inject Lacuna meta tags so the library detects the extension ──
  function injectMetaTags() {
    var head = document.head || document.documentElement;
    for (var i = 0; i < LACUNA_META_IDS.length; i++) {
      if (!document.getElementById(LACUNA_META_IDS[i])) {
        var meta = document.createElement('meta');
        meta.id = LACUNA_META_IDS[i];
        head.appendChild(meta);
      }
    }
  }

  // Inject immediately (document_start) and also on DOMContentLoaded
  injectMetaTags();
  document.addEventListener('DOMContentLoaded', injectMetaTags);

  // ── 2. Bridge: Lacuna library → Softplan content script ──
  window.addEventListener('message', function (event) {
    if (!event || !event.data || !event.data.port) return;

    // Lacuna library sends request → forward to Softplan content script
    if (event.data.port === LACUNA_REQUEST) {
      window.postMessage({
        port: SOFTPLAN_REQUEST,
        message: event.data.message
      }, '*');
    }

    // Softplan content script sends response → forward to Lacuna library
    if (event.data.port === SOFTPLAN_RESPONSE) {
      window.postMessage({
        port: LACUNA_RESPONSE,
        message: event.data.message
      }, '*');
    }
  });
})();
