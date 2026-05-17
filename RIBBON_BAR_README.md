# HealthReport Studio - Ribbon Bar

## Descrizione

La ribbon bar è una barra di strumenti moderna e intuitiva posizionata sopra i tab principali dell'applicazione. Organizza le funzioni generali in gruppi logici con icone SVG personalizzate.

## Struttura della Ribbon Bar

### Gruppi di funzioni:

1. **File**
   - 📄 Nuovo progetto: Crea un nuovo progetto azzerando i dati
   - 📂 Apri file: Apre un file di progetto (non ancora implementato)
   - 💾 Salva: Salva il dataset in CSV o Excel

2. **Dati**
   - ⬆️ Importa dataset: Accede al tab di import dati
   - ⬇️ Esporta dataset: Accede al tab di export
   - 🔄 Aggiorna: Aggiorna qualità e KPI

3. **Report**
   - 🖨️ Stampa report: Esporta il report in PDF

4. **Strumenti**
   - ⚙️ Impostazioni: Mostra opzioni di configurazione
   - ❓ Aiuto: Visualizza la guida dell'applicazione
   - ℹ️ Informazioni: Mostra info sull'app

## Architettura dei file

### File nuovo creati:

- **ribbon_bar.py**: Modulo che contiene le classi `RibbonGroup` e `RibbonBar`
- **resources.qrc**: File di risorse Qt (dichiarazione delle icone)
- **icons/**: Cartella con icone SVG personalizzate

### File modificati:

- **main.py**: 
  - Importa `RibbonBar` da `ribbon_bar`
  - Integra la ribbon bar nel layout principale
  - Aggiunge handler per tutti i pulsanti della ribbon bar

## Come estendere la Ribbon Bar

### Aggiungere un nuovo gruppo:

```python
# Nel metodo init_ui di RibbonBar
custom_group = RibbonGroup("Nome Gruppo")
custom_group.add_button(
    "icons/icon.svg", 
    "Tooltip",
    self.custom_signal.emit
)
main_layout.addWidget(custom_group)
```

### Aggiungere un nuovo segnale:

```python
# In RibbonBar
custom_pressed = Signal()

# Nello slot del pulsante
self.custom_btn = custom_group.add_button(
    "icons/icon.svg",
    "Tooltip",
    self.custom_pressed.emit
)
```

### Aggiungere nuove icone:

1. Creare il file SVG in `icons/icon.svg`
2. Aggiungere la voce in `resources.qrc`
3. Usare il percorso in `add_button()`

## Icone SVG utilizzate

- **new.svg**: Documento nuovo
- **open.svg**: Cartella aperta
- **save.svg**: Documento con freccia su (salva)
- **import.svg**: Freccia in alto
- **export.svg**: Freccia in basso
- **print.svg**: Stampante
- **settings.svg**: Ruota dentata
- **help.svg**: Punto interrogativo in cerchio
- **about.svg**: Frecce circolari (informazioni)
- **refresh.svg**: Frecce ricircolari (aggiorna)

## Stile CSS personalizzato

I pulsanti hanno stati visivi:
- **Normal**: Sfondo trasparente
- **Hover**: Sfondo azzurro chiaro (#e8f4f8)
- **Pressed**: Sfondo azzurro più scuro (#cce5f0)

## Handler dei pulsanti

| Pulsante | Metodo | Azione |
|----------|--------|--------|
| Nuovo | `on_new_project()` | Azzera il dataset |
| Apri | `on_open_file()` | Apre file (futura implementazione) |
| Salva | `on_save_file()` | Salva dataset in CSV/Excel |
| Importa | `on_import_data()` | Naviga al tab Import |
| Esporta | `on_export_data()` | Naviga al tab Export |
| Stampa | `on_print_report()` | Esporta report PDF |
| Aggiorna | `on_refresh_data()` | Aggiorna qualità e KPI |
| Impostazioni | `on_settings()` | Mostra menu impostazioni |
| Aiuto | `on_help()` | Mostra guida |
| Informazioni | `on_about()` | Mostra info app |

## Esecuzione

L'app si avvia normalmente tramite venv:

```bash
./venv/bin/python3 main.py
```

La ribbon bar è automaticamente caricata e visibile sotto la barra del titolo.

## Future migliorie

- Menu a tendina nei gruppi per funzioni avanzate
- Pulsanti separatori tra gruppi
- Personalizzazione layout ribbon bar (auto-hide, collapse)
- Icone dinamiche basate su tema (scuro/chiaro)
- Animazioni al passaggio del mouse
