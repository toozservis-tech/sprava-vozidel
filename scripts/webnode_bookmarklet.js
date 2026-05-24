// Bookmarklet pro automatické vložení HTML do Webnode editoru
// Použití: Zkopírujte celý tento kód a vytvořte z něj bookmarklet

javascript:(function(){
    // Načíst HTML z API nebo zobrazit dialog
    const loadHTML = async () => {
        try {
            // Zkusit načíst z API (pokud běží server)
            const apiUrl = window.prompt('Zadejte URL k API serveru (např. https://hub.toozservis.cz nebo http://127.0.0.1:8001):', 'https://hub.toozservis.cz');
            if (!apiUrl) return null;
            const response = await fetch(`${apiUrl}/web/index.html`, {
                headers: {'Content-Type': 'text/html'}
            });
            if (response.ok) {
                return await response.text();
            }
        } catch (e) {
            console.log('API neodpovídá, použiji fallback');
        }
        
        // Fallback - zobrazit dialog pro vložení URL nebo textu
        const url = prompt('Zadejte URL k HTML souboru (nebo nechte prázdné pro vložení z clipboardu):');
        if (url) {
            try {
                const response = await fetch(url);
                if (response.ok) {
                    return await response.text();
                }
            } catch (e) {
                alert('Nepodařilo se načíst HTML z URL');
            }
        }
        return null;
    };
    
    const insertHTML = async () => {
        const html = await loadHTML();
        if (!html) {
            // Zkusit získat z clipboardu
            try {
                const text = await navigator.clipboard.readText();
                if (text && text.includes('<!DOCTYPE html>')) {
                    insertIntoEditor(text);
                    return;
                }
            } catch (e) {
                console.log('Clipboard API není dostupné');
            }
            alert('Nepodařilo se načíst HTML. Zkopírujte HTML do clipboardu a zkuste znovu.');
            return;
        }
        insertIntoEditor(html);
    };
    
    const insertIntoEditor = (html) => {
        // Hledat textarea nebo iframe editoru Webnode
        const textareas = document.querySelectorAll('textarea');
        const iframes = document.querySelectorAll('iframe');
        
        // Zkusit najít editor Webnode
        for (let textarea of textareas) {
            if (textarea.style.display !== 'none' && textarea.offsetHeight > 0) {
                textarea.value = html;
                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                textarea.dispatchEvent(new Event('change', { bubbles: true }));
                alert('✓ HTML vloženo do editoru!');
                return;
            }
        }
        
        // Zkusit najít CodeMirror nebo jiný editor
        if (window.CodeMirror) {
            const editors = document.querySelectorAll('.CodeMirror');
            if (editors.length > 0) {
                const cm = editors[0].CodeMirror;
                if (cm) {
                    cm.setValue(html);
                    alert('✓ HTML vloženo do CodeMirror editoru!');
                    return;
                }
            }
        }
        
        // Fallback - zobrazit dialog
        const htmlText = prompt('HTML kód (vložte ručně do editoru):', html.substring(0, 500) + '...');
        if (htmlText) {
            // Zkusit zkopírovat do clipboardu
            if (navigator.clipboard) {
                navigator.clipboard.writeText(html).then(() => {
                    alert('✓ HTML zkopírováno do clipboardu! Vložte do editoru (Ctrl+V)');
                });
            }
        }
    };
    
    insertHTML();
})();



