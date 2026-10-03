# Regole permanenti di rilascio

- Prima di ogni release, applicare RELEASE_CHECKLIST.md e registrare gli esiti nelle note di rilascio.
- Mantenere R11 (interfaccia) e R12 (dipendenze e file) come attività ricorrenti nella roadmap, senza chiuderle definitivamente dopo una sola release.
- Aggiornare l’interfaccia in coerenza con le funzionalità e verificare i flussi interessati, leggibilità, ridimensionamento, navigazione e stati di errore/vuoto.
- Rimuovere dipendenze o file solo dopo verifica dell’uso diretto/dinamico, dei profili opzionali, dei test e della documentazione. Correggere o sostituire elementi necessari ma incompatibili; preservare dati operativi, fonti e migrazioni necessarie.
- Distinguere sempre controlli realmente eseguiti, limiti e funzionalità ancora pianificate. Una checklist presente non equivale a una checklist completata.
