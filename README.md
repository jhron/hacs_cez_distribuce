# ČEZ Distribuce – Home Assistant custom komponenta

Tato integrace se připojí k portálu ČEZ Distribuce a zveřejní do Home Assistanta:

- binární senzor informující, zda je aktuálně nízký tarif (NT)
- kalendář nízkého tarifu (HDO) s časy spínání
- kalendář plánovaných odstávek
- senzory s posledními stavy VT, NT a součtem (pro reporty/energie)

Integrace používá klienta `custom_components.cez_distribuce.rest_client.rest_client.CezDistribuceRestClient` a vyžaduje přístupové údaje k portálu.

Upozornění: Jedná se o neoficiální integraci. Používejte na vlastní riziko.

## Instalace

1. Zkopírujte celý adresář `custom_components/cez_distribuce` do adresáře `custom_components` ve vaší instalaci Home Assistanta.
2. Restartujte Home Assistant.

## Konfigurace (configuration.yaml)

```yaml
cez_distribuce:
  username: "VASE_UZIVATELSKE_JMENO"
  password: "VASE_HESLO"
  # volitelně intervaly aktualizace (v minutách):
  # scan_interval_signals: 360
  # scan_interval_outages: 360
  # scan_interval_readings: 1440

# Volitelně můžete povolit platformy také přes discovery, integrace je načte automaticky:
# binary_sensor:
#   - platform: cez_distribuce
# calendar:
#   - platform: cez_distribuce
# sensor:
#   - platform: cez_distribuce
```

Po restartu integrace vytvoří:

- `binary_sensor.nizky_tarif` (název "Nízký tarif") – zapnuto, když je právě NT podle signálů HDO.
- Kalendář "HDO – nízký tarif" – obsahuje události NT z dat HDO.
- Kalendář "ČEZ Odstávky" – obsahuje plánované odstávky pro vaše OM/EAN.
- Senzory:
  - "Poslední stav VT" (kWh)
  - "Poslední stav NT" (kWh)
  - "Poslední stav celkem" (kWh)

Poznámky:
- Integrace aktuálně pracuje s prvním nalezeným odběrným místem (OM) ve vašem účtu.
- Nízký tarif je odvozen ze seznamu časů v odpovědi "Signály". Pokud portál HDO pro vaše OM není dostupný, senzor zůstane vypnutý a kalendář bude prázdný.
- Odstávky se načítají podle EAN vašeho OM.

## Konfigurace přes UI (Config Flow)

Integraci lze přidat také přes Nastavení → Zařízení a služby → Přidat integraci → „ČEZ Distribuce“. Budete vyzváni k zadání uživatelského jména a hesla do portálu ČEZ Distribuce. Při ověřování přihlášení se integrace pokusí připojit a načíst základní informace. Pokud přihlášení selže, uvidíte chybu:
- „invalid_auth“ – nesprávné jméno nebo heslo
- „cannot_connect“ – služba je nedostupná nebo došlo k jiné chybě připojení

## Testy

Repozitář obsahuje základní jednotkové testy pro pomocné funkce REST klienta. Testy spustíte lokálně takto:

- nainstalujte závislosti pro testování (pytest):
  - python -m pip install -U pytest
- spusťte testy v kořenovém adresáři repozitáře:
  - pytest -q

> Pozn.: Testy nevyžadují přímé připojení k portálu a neprovádějí žádné reálné přihlášení.


## Přehled projektu

Tato neoficiální integrace pro Home Assistant přináší do vašeho chytrého domu informace z portálu ČEZ Distribuce. Zaměřuje se na praktické funkce pro automatizace:
- dostupnost nízkého tarifu (NT, HDO) pro řízení spotřebičů,
- kalendář HDO pro přehled spínacích oken,
- kalendář plánovaných odstávek,
- poslední stavové hodnoty elektroměru (VT/NT/celkem) pro reporty a energetické přehledy.

Architektura integrace:
- REST klient pro přihlášení a čtení dat z webového portálu ČEZ Distribuce (synchronní volání přes requests),
- CezHub, který zajišťuje přihlášení, jednorázové načtení statických dat a periodické aktualizace vybraných částí,
- platformy Home Assistanta: binary_sensor, calendar a sensor.

Upozornění: Integrace není oficiální. Portál se může měnit a způsobit dočasné výpadky funkčnosti. Používejte na vlastní riziko.

## Požadavky
- Home Assistant (doporučeno 2023.0+).
- Aktivní účet k portálu ČEZ Distribuce s přístupem k vašim OM/EAN.
- Stabilní internetové připojení ze strany Home Assistanta.

## Instalace přes HACS
Je-li ve vašem HA nainstalován HACS:
1. V HACS otevřete Integrations → menu vpravo nahoře → Custom repositories.
2. Přidejte URL tohoto repozitáře jako „Integration“.
3. Vyhledejte „ČEZ Distribuce“ a nainstalujte.
4. Restartujte Home Assistant.
5. Přidejte integraci přes UI (viz níže).

## Manuální instalace (shrnutí)
- Zkopírujte adresář `custom_components/cez_distribuce` do stejnojmenné složky ve vaší instalaci Home Assistanta.
- Restartujte Home Assistant.

## Konfigurace přes UI (Config Flow) – podrobněji
Integraci přidejte v Nastavení → Zařízení a služby → Přidat integraci → „ČEZ Distribuce“. Zadejte uživatelské jméno a heslo do portálu ČEZ Distribuce. Při ověření přihlášení se vyzkouší přístup k portálu.
- Chyba „invalid_auth“ značí chybné údaje.
- Chyba „cannot_connect“ značí problém s dostupností služby či připojením.

Volitelné intervaly aktualizace lze nastavit až po vytvoření záznamu integrace (v budoucnu mohou být přidány do rozšířeného dialogu). Výchozí hodnoty:
- signály (HDO): 360 min
- odstávky: 360 min
- odečty: 1440 min

## Konfigurace v configuration.yaml (alternativa)
Základní příklad je uveden výše v této stránce. Volitelné klíče pro intervaly:
- `scan_interval_signals` – v minutách
- `scan_interval_outages` – v minutách
- `scan_interval_readings` – v minutách

## Vytvářené entity – detail
- binary_sensor.nizky_tarif
  - Stav „on“ v oknech nízkého tarifu dle HDO signálů pro první dostupné OM.
- Kalendář „HDO – nízký tarif“
  - Události s obdobími, kdy je NT aktivní.
- Kalendář „ČEZ Odstávky“
  - Naplánované odstávky dle EAN vašeho OM.
- Senzory odečtů:
  - Poslední stav VT (kWh), Poslední stav NT (kWh), Poslední stav celkem (kWh).

Poznámky a omezení:
- Aktuálně se pracuje s prvním nalezeným odběrným místem v účtu.
- Pokud pro OM nejsou dostupné HDO signály, kalendář HDO bude prázdný a binární senzor zůstane vypnutý.
- V případě dočasného výpadku portálu se integrace snaží použít poslední známá data.

## Příklady použití

1) Automatické zapnutí bojleru pouze během NT:

```yaml
alias: Zapnout bojler v NT
trigger:
  - platform: state
    entity_id: binary_sensor.nizky_tarif
    to: 'on'
action:
  - service: switch.turn_on
    target:
      entity_id: switch.bojler
```

2) Vypnutí bojleru po konci NT:

```yaml
alias: Vypnout bojler mimo NT
trigger:
  - platform: state
    entity_id: binary_sensor.nizky_tarif
    to: 'off'
action:
  - service: switch.turn_off
    target:
      entity_id: switch.bojler
```

3) Zobrazení příštího okna NT z kalendáře v šabloně:

```yaml
sensor:
  - platform: template
    sensors:
      pristi_nt:
        friendly_name: "Příští NT okno"
        value_template: >-
          {{ state_attr('calendar.hdo_nizky_tarif','start_time') }} – {{ state_attr('calendar.hdo_nizky_tarif','end_time') }}
```

## Řešení problémů
- Ověřte, že se přihlásíte do portálu ČEZ Distribuce se stejnými údaji v běžném prohlížeči.
- V Nastavení → Systém → Záznamy zapněte ladicí logování pro komponentu, např. v configuration.yaml:

```yaml
logger:
  default: warning
  logs:
    custom_components.cez_distribuce: debug
```

- Dočasné chyby portálu mohou vést k „cannot_connect“. Zkuste to znovu později.
- Po změně hesla odeberte a znovu přidejte integraci.

## Soukromí a zabezpečení
- Přihlašovací údaje jsou uloženy v bezpečném úložišti Home Assistanta a používány pouze pro načítání údajů z portálu.
- Integrace neodesílá data třetím stranám mimo ČEZ Distribuce.

## Vývoj a přispívání
- Testy spustíte lokálně pomocí `pytest -q` (viz kapitola Testy výše).
- Pull Requesty s vylepšeními a opravami jsou vítány. Prosíme o stručný popis změn a doplnění testů, pokud je to možné.

## Nahlášení chyb a návrhy
- Otevírejte prosím issues v GitHub repozitáři s co nejpřesnějším popisem problému, výpisem z logu a verzí HA.

## Licence
Distribuováno pod licencí uvedenou v souboru LICENSE tohoto repozitáře.

## Poděkování
Díky komunitě Home Assistant a projektu HACS za nástroje a inspiraci.
