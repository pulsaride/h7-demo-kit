# Fixtures — h7-demo-kit

`baseline.example.json` doit être une baseline H7 v0.2.0+ valide (Gate Alpha
PASS, sha256 self-référencé) calibrée sur la machine de démo.

## Comment la générer

Sur la machine cible (idéalement en idle) :

```sh
sudo h7-sensor --mode calibrate \
    --duration 1800 \
    --output ./baseline.example.json
```

Puis :
- copier le `.cal` sidecar généré (sera utilisé par `make verify`)
- recopier les deux fichiers ici : `cp baseline.example.json* fixtures/`

## Pourquoi c'est une « example » et pas une « default »

La baseline est **machine-spécifique** (cgroup ID, μ, h_threshold dérivés).
La rejouer sur une autre machine fera FAIL au démarrage du monitor
(intégrité sha256 OK mais Gate Alpha refusera si la signature κ ne
correspond plus à l'environnement). C'est **voulu** : pas d'illusion de
portabilité.
