# 💬 Command Bot v1 - Dokumentace

## 📍 Kde najdete Command Bota

### 1. **Admin Dashboard UI**
Command Bot je dostupný v **Developer Admin Dashboard**:

**Cesta:**
- Otevřete: `http://localhost:8000/web_admin/index.html` (nebo vaše produkční URL)
- Přihlaste se jako `developer_admin`
- V levém sidebaru klikněte na **"💬 Příkazy zákazníků"**

**Funkce:**
- Zobrazení všech příkazů zákazníků v tabulce
- Filtrování podle statusu (Přijato, Zpracováno, Chyba)
- Filtrování podle typu záměru (Rezervace, Úkol, Poznámka, Otázka, Neznámé)
- Vyhledávání podle zákazníka nebo textu příkazu
- Detail každého příkazu
- Otevření vozidla (pokud je vazba)

### 2. **Backend API Endpointy**

#### POST `/api/customer-commands`
Vytvoří nový zákaznický příkaz a automaticky ho zpracuje.

**Request:**
```json
{
  "source": "web_chat",
  "customer_name": "Jan Novák",
  "customer_email": "jan@example.com",
  "vehicle_id": 123,
  "message": "Chci se objednat na výměnu oleje"
}
```

**Response:**
```json
{
  "intent_type": "CREATE_BOOKING",
  "status": "EXECUTED",
  "result_summary": "Vytvořena rezervace ID 456 – čeká na potvrzení.",
  "command_id": 789
}
```

#### GET `/api/customer-commands`
Získá seznam příkazů zákazníků.

**Query parametry:**
- `limit` (default: 50)
- `offset` (default: 0)
- `status` (volitelné: RECEIVED, EXECUTED, FAILED)
- `intent_type` (volitelné: CREATE_BOOKING, CREATE_TASK, ADD_NOTE, QUESTION, UNKNOWN)

#### GET `/api/customer-commands/{command_id}`
Získá detail konkrétního příkazu.

### 3. **Automatické napojení**

Command Bot je automaticky napojen na:
- **TooZ Autopilot** - každá zpráva z autopilota se zaznamená jako příkaz
- **AI Endpoint** (`/api/v1/ai/record`) - při vytvoření servisního záznamu z AI se také vytvoří záznam příkazu

## 🔧 Jak to funguje

### Intent Detection (Rozpoznávání záměru)

Bot používá jednoduché pravidlo-based rozpoznávání:

1. **CREATE_BOOKING** - klíčová slova: "objednat", "termín", "servis", "rezervace", atd.
2. **CREATE_TASK** - klíčová slova: "připomeň", "úkol", "nezapomeň", atd.
3. **ADD_NOTE** - klíčová slova: "poznámka", "zapiš si", "zapsat", atd.
4. **QUESTION** - text končící otazníkem
5. **UNKNOWN** - vše ostatní

### Automatické akce

Podle rozpoznaného záměru bot automaticky:

- **CREATE_BOOKING** → Vytvoří rezervaci (status PENDING)
- **CREATE_TASK** → Vytvoří připomínku/úkol
- **ADD_NOTE** → Přidá poznámku k vozidlu (nebo vytvoří servisní záznam)
- **QUESTION/UNKNOWN** → Jen zaznamená, čeká na ruční zpracování

## 📊 Databázový model

Tabulka `customer_commands` obsahuje:
- `id` - primární klíč
- `created_at` - datum vytvoření
- `source` - zdroj ("web_chat", "autopilot", "internal")
- `customer_name`, `customer_email` - identifikace zákazníka
- `vehicle_id` - vazba na vozidlo (volitelné)
- `raw_text` - původní text příkazu
- `normalized_text` - připraveno pro budoucí AI
- `intent_type` - rozpoznaný záměr
- `status` - RECEIVED, EXECUTED, FAILED
- `result_summary` - výsledek zpracování
- `error_message` - chybová zpráva (pokud selhalo)

## 🚀 Použití

### Z web chatu / autopilota

Při odeslání zprávy zákazníka automaticky zavolejte:

```javascript
await fetch('/api/customer-commands', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    source: 'web_chat',
    customer_name: customerName,
    customer_email: customerEmail,
    vehicle_id: currentVehicleId,
    message: userMessage
  })
});
```

### Z admin dashboardu

1. Otevřete Admin Dashboard
2. Klikněte na "💬 Příkazy zákazníků" v sidebaru
3. Prohlížejte, filtrujte a spravujte příkazy

## 🔮 Budoucí rozšíření

- **AI integrace** - nahrazení pravidlo-based detekce AI modelem
- **Automatické odpovědi** - bot může automaticky odpovídat zákazníkům
- **Více typů akcí** - rozšíření o další automatické akce
- **Notifikace** - upozornění adminům na nové příkazy

## 📝 Poznámky

- Bot **nerozbíjí** stávající funkcionalitu - jen přidává nové možnosti
- Všechny příkazy jsou **logovány** v databázi
- Automatické akce jsou **bezpečné** - jen vytvářejí záznamy, nic nemazají
- Pro v1 je automatické zpracování **jednoduché** - připraveno na rozšíření







