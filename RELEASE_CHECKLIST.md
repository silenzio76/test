# Checklist permanente per ogni release

Applicare a ogni versione del progetto, anche dopo il primo completamento degli incrementi R11–R12. Registrare gli esiti nelle note di rilascio con versione/commit, data, verificatore, modifiche, controlli e limitazioni. Le voci non applicabili richiedono una motivazione; gli impedimenti alle funzionalità dichiarate bloccano il rilascio.

## Interfaccia — R11

- [ ] Schermate, comandi e terminologia aggiornati rispetto alle funzionalità effettivamente disponibili; elementi dimostrativi o non utilizzabili identificati e corretti.
- [ ] Flussi coinvolti provati: prenotazione/stati, import, statistiche, report e ML secondo l’ambito della release.
- [ ] Controllati leggibilità, navigazione da tastiera, etichette, ridimensionamento e scorrimento; dati osservati, simulazioni e previsioni distinguibili.
- [ ] Verificati stati vuoti, caricamento, errori, validazione degli input e messaggi di esito; nessun risultato precedente presentato come risultato di un’operazione fallita.
- [ ] Registrati problemi risolti, verifica funzionale e visiva pertinente e limitazioni residue. Anche in assenza di modifiche grafiche, registrata la revisione.

## Dipendenze e file — R12

- [ ] Inventariati dipendenze e file candidati alla pulizia; per ogni candidato verificati riferimenti nel codice, import dinamici, funzionalità opzionali, test, script e documentazione.
- [ ] Verificate compatibilità e installabilità dei profili necessari con le versioni Python dichiarate; eventuali profili opzionali non verificati indicati esplicitamente.
- [ ] Rimossi elementi confermati inutili, obsoleti o duplicati; elementi necessari ma inutilizzabili corretti o sostituiti. Conservata una motivazione per ogni intervento.
- [ ] Conservati fonti, licenze, migrazioni, fixture e anagrafiche ancora necessarie; rimossi artefatti generati solo quando rigenerabili e non richiesti. Nessuna cancellazione dei dati operativi come parte della pulizia.
- [ ] Allineati requirements, cataloghi core/opzionali, configurazioni e istruzioni di avvio. Le librerie richieste per il profilo scientifico non sono considerate inutili per il solo mancato uso nel core.
- [ ] Verificati avvio e funzioni interessate dopo la pulizia, con test pertinenti; nessuna regressione lasciata aperta nelle funzionalità dichiarate.

## Chiusura del rilascio

- [ ] Note di rilascio distinguono implementato, pianificato e non verificato; includono esiti R11–R12 e cambi di compatibilità/formato.
- [ ] Verificati diff, contenuto pubblicato e assenza di database operativi, credenziali o artefatti locali estranei alla release.
- [ ] Commit e destinazione di pubblicazione verificati; limiti e problemi rinviati hanno una voce di backlog esplicita.

Questa checklist definisce i controlli da eseguire; la sua presenza nel repository non dimostra che siano stati completati per una particolare release.
