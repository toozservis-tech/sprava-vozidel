# Vytvoření administrátorského účtu (developer_admin)

Pro plný admin přístup do `web_admin` použijte roli `developer_admin`.

## 1) Vytvoření nového admin účtu

```bash
cd /opt/toozhub2/app
python3 scripts/create_developer_admin.py \
  --email admin@domena.cz \
  --password 'SilneHeslo123' \
  --name 'Hlavní administrátor'
```

## 2) Povýšení existujícího účtu na admina

```bash
cd /opt/toozhub2/app
python3 scripts/create_developer_admin.py --email toozservis@gmail.com
```

Volitelně můžete zároveň změnit heslo:

```bash
python3 scripts/create_developer_admin.py \
  --email toozservis@gmail.com \
  --password 'NoveSilneHeslo123'
```

## 3) Přihlášení do admin rozhraní

Admin UI je dostupné na:

`/web_admin/`

např. `https://hub.toozservis.cz/web_admin/`
