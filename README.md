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
