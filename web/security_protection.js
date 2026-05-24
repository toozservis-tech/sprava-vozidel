/**
 * Security Protection - Anti-debugging a ochrana proti odcizení kódu
 * Správa vozidel - Proprietary Software
 * Všechna práva vyhrazena.
 */

(function() {
    'use strict';
    
    const ENVIRONMENT = 'development'; // development | production - ZMĚNĚNO na development aby neskrývala aplikaci
    
    // ============= ANTI-DEBUGGING =============
    
    // Detekce DevTools
    function detectDevTools() {
        let devtools = false;
        const threshold = 160;
        
        setInterval(() => {
            if (window.outerHeight - window.innerHeight > threshold || 
                window.outerWidth - window.innerWidth > threshold) {
                if (!devtools) {
                    devtools = true;
                    handleDevToolsOpen();
                }
            } else {
                devtools = false;
            }
        }, 500);
    }
    
    // Detekce konzole
    function detectConsole() {
        let consoleOpen = false;
        
        const detect = () => {
            const start = performance.now();
            console.log('%c', '');
            const end = performance.now();
            
            if (end - start > 100) {
                if (!consoleOpen) {
                    consoleOpen = true;
                    handleConsoleOpen();
                }
            }
        };
        
        setInterval(detect, 1000);
    }
    
    // Zakázat kontextové menu (pravé tlačítko)
    function disableContextMenu() {
        document.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            return false;
        }, false);
        
        // Zakázat F12, Ctrl+Shift+I, Ctrl+Shift+J, Ctrl+U
        document.addEventListener('keydown', (e) => {
            if (e.key === 'F12' ||
                (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'J' || e.key === 'C')) ||
                (e.ctrlKey && e.key === 'U')) {
                e.preventDefault();
                return false;
            }
        }, false);
    }
    
    // Zakázat text selection (v produkci)
    function disableTextSelection() {
        if (ENVIRONMENT === 'production') {
            document.addEventListener('selectstart', (e) => {
                e.preventDefault();
                return false;
            }, false);
            
            // CSS
            const style = document.createElement('style');
            style.textContent = `
                * {
                    -webkit-user-select: none !important;
                    -moz-user-select: none !important;
                    -ms-user-select: none !important;
                    user-select: none !important;
                }
            `;
            document.head.appendChild(style);
        }
    }
    
    // Zakázat kopírování (v produkci)
    function disableCopy() {
        if (ENVIRONMENT === 'production') {
            document.addEventListener('copy', (e) => {
                e.preventDefault();
                e.clipboardData.setData('text/plain', '');
                return false;
            }, false);
            
            document.addEventListener('cut', (e) => {
                e.preventDefault();
                return false;
            }, false);
        }
    }
    
    // Zakázat drag & drop
    function disableDragDrop() {
        document.addEventListener('dragstart', (e) => {
            e.preventDefault();
            return false;
        }, false);
    }
    
    // ============= HANDLERS =============
    
    function handleDevToolsOpen() {
        if (ENVIRONMENT === 'production') {
            console.clear();
            console.log('%c⚠️ WARNING', 'color: red; font-size: 50px; font-weight: bold;');
            console.log('%cThis is a browser feature intended for developers.', 'color: red; font-size: 20px;');
            console.log('%cIf someone told you to paste something here, it is a scam!', 'color: red; font-size: 20px;');
            
            // VYPNUTO - aby aplikace nemizela
            // setTimeout(() => {
            //     window.location.href = 'about:blank';
            // }, 1000);
        }
    }
    
    function handleConsoleOpen() {
        if (ENVIRONMENT === 'production') {
            console.clear();
            console.log('%c⚠️ UNAUTHORIZED ACCESS DETECTED', 'color: red; font-size: 30px; font-weight: bold;');
            console.log('%cThis software is protected by copyright.', 'color: red; font-size: 20px;');
        }
    }
    
    // ============= LICENSE WATERMARK =============
    
    function addWatermark() {
        const watermark = document.createElement('div');
        watermark.id = 'sprava-vozidel-watermark';
        watermark.style.cssText = `
            position: fixed;
            bottom: 10px;
            right: 10px;
            opacity: 0.1;
            font-size: 10px;
            color: #000;
            pointer-events: none;
            z-index: 9999;
            font-family: monospace;
        `;
        watermark.textContent = 'Správa vozidel – proprietary software. Všechna práva vyhrazena.';
        document.body.appendChild(watermark);
    }
    
    // ============= INITIALIZATION =============
    
    function init() {
        if (ENVIRONMENT === 'production') {
            detectDevTools();
            detectConsole();
            disableContextMenu();
            disableTextSelection();
            disableCopy();
            disableDragDrop();
        }
        addWatermark();
    }
    
    // Spustit po načtení
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
})();
