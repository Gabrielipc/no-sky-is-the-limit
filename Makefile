export PIXI_HOME := $(CURDIR)/.tools/pixi
PIXI := ./.tools/pixi/bin/pixi
.PHONY: help setup backend frontend test build check check-env analysis test-analysis

help:
	@printf '%s\n' 'setup          Inicializa Pixi y las dependencias' 'backend        Inicia la API' 'frontend       Inicia el frontend' 'test           Ejecuta las pruebas existentes' 'build          Compila el frontend' 'check-env      Comprueba los CRS planetarios' 'check          Ejecuta las comprobaciones' 'analysis       Reproduce el primer análisis regional (datos locales)' 'test-analysis  Comprueba métricas y máscaras del análisis regional'
setup:
	./scripts/inicializar.sh
backend:
	$(PIXI) run backend
frontend:
	$(PIXI) run frontend
test:
	$(PIXI) run test
build:
	$(PIXI) run build
check-env:
	$(PIXI) run check-env
check: check-env test build
analysis:
	$(PIXI) run analysis
test-analysis:
	$(PIXI) run test-analysis
