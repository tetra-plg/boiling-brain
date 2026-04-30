# Mémoire — {{domain_label}}-expert

> Cette mémoire est lue par `{{domain_slug}}-expert` au démarrage de chaque ingest, et mise à jour en fin d'ingest. Elle représente l'**état du domaine** dans le wiki — pas des règles comportementales (celles-ci vivent dans le prompt système et évoluent via `/evolve-agent`).
>
> Format : sections nommées avec entrées datées `[last-seen: YYYY-MM-DD]`. Une entrée disparaît dès qu'elle est confirmée (concept créé, pattern codifié) ou archivée si elle traîne > 90 jours sans suite.

## Patterns en attente

> Patterns observés dans une seule source — j'attends une 2e occurrence avant de créer la page concept correspondante (cf. règle « ≥2 sources » du wiki). Si une nouvelle source confirme l'un d'eux, je crée la page maintenant et je retire l'entry.

_(vide à l'amorçage)_

## Concepts récents

> Liste des 10 derniers concepts que j'ai créés ou enrichis significativement, par date décroissante. Sert à éviter les doublons et à proposer des cross-refs naturelles dans les ingestions à venir.

_(vide à l'amorçage)_

## Sources pivots

> Sources particulièrement structurantes du domaine — cadrent un sous-thème entier. À garder en tête pour les cross-refs.

_(vide à l'amorçage)_

## Patterns expirés

> Archive des entries restées trop longtemps en attente (> 90 jours) ou écartées. Pas supprimées — elles peuvent redevenir pertinentes.

_(vide à l'amorçage)_
