"""Publica salidas verificadas del Colab sin registros individuales ni widgets."""

import argparse
import hashlib
import re
from pathlib import Path

import nbformat
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def public_outputs(cell):
    """Salidas que se pueden publicar: sin widgets, sin tablas de avisos y sin rutas locales."""
    visible = []
    for output in cell.outputs:
        data = output.get('data', {})
        if 'application/vnd.jupyter.widget-view+json' in data:
            continue
        if cell.id in {'explorador', 'inferencia'} and output.output_type in {'display_data', 'execute_result'}:
            continue
        if output.output_type == 'stream':
            output.text = re.sub(r'[A-Za-z]:[\\/][^\r\n]*', '[ruta local omitida]', output.text)
        visible.append(output)
    return visible


def clean_cell(cell):
    """Deja solo las salidas publicables y quita el estado de vista de la celda."""
    cell.outputs = public_outputs(cell)
    for key in ['collapsed', 'scrolled', 'jupyter']:
        cell.metadata.pop(key, None)


def publish(source, destination):
    notebook = nbformat.read(source, as_version=4)
    nbformat.validate(notebook)
    code = [cell for cell in notebook.cells if cell.cell_type == 'code']
    if not code or any(cell.execution_count is None for cell in code):
        raise ValueError('La fuente debe tener todas sus celdas ejecutadas.')
    if any(output.output_type == 'error' for cell in code for output in cell.outputs):
        raise ValueError('La fuente contiene errores de ejecución.')
    required = {'benchmark', 'comparacion', 'residuos', 'subgrupos', 'interpretacion',
                'anexo-validacion-temporal'}
    if not required.issubset({cell.id for cell in notebook.cells}):
        raise ValueError('Faltan resultados o el anexo temporal en la fuente.')

    # Las tablas de avisos individuales se conservan solo en la entrega privada.
    for cell in code:
        clean_cell(cell)
    notebook.metadata.pop('widgets', None)

    notice = nbformat.v4.new_markdown_cell("""## Lectura de resultados sin ejecutar

Este notebook conserva una ejecución completa del benchmark: tablas de métricas, nueve figuras y diagnósticos. La profesora puede leerlo directamente en GitHub o Colab, sin instalar dependencias ni subir el paquete de datos. Las salidas corresponden a la ejecución histórica indicada en la celda del benchmark; abrirlo no entrena de nuevo.

El Anexo A presenta por separado la evaluación temporal del HGB operativo. Las tablas de avisos individuales y los widgets se omiten de la vista pública; su código permanece disponible para ejecución con los insumos autorizados. Las métricas y conclusiones agregadas sí están visibles.

Para repetir el análisis, hace falta el paquete privado `capstone_bundle.zip`. La configuración conserva el valor usado en la ejecución original; antes de ejecutar, elegir `REENTRENAR=False` para reutilizar evidencia o `True` para repetir el benchmark completo. Los modelos no predicen precios de cierre ni acreditan oportunidades de inversión.
""", id='lectura-publica')
    # Repetir la publicación no duplica las notas editoriales.
    notebook.cells = [cell for cell in notebook.cells if cell.id not in {'lectura-publica', 'conclusiones-modelos-publicas'}]
    notebook.cells.insert(1, notice)
    summary = pd.read_csv(ROOT / 'reports/benchmark-auditado/resumen.csv')
    models = ['Ridge', 'KNN', 'Random Forest', 'HistGradientBoosting', 'MLP']
    table = summary[summary.model.isin(models) & summary.scope.eq('edificio')].sort_values('mae')
    if len(table) != 5:
        raise ValueError('Se requieren las cinco familias del escenario edificio.')
    benchmark_text = '\n'.join(str(output.get('text', '')) + str(output.get('data', {}).get('text/plain', ''))
                               for cell in notebook.cells if cell.id == 'benchmark' for output in cell.outputs)
    for row in table.itertuples():
        if f'{row.mae:.6f}' not in benchmark_text:
            raise ValueError(f'La fuente ejecutada no coincide con el reporte: {row.model}')
    fmt = lambda value, places=2: f'{value:.{places}f}'.replace('.', ',')
    rows = ['| ' + ' | '.join([row.model, fmt(row.mae), fmt(row.rmse), fmt(row.r2, 3), fmt(row.mdape_pct)]) + ' |'
            for row in table.itertuples()]
    best = table.iloc[0]
    baseline = summary[summary.model.eq('Mediana comparables')].iloc[0]
    improvement = 100 * (1 - best.mae / baseline.mae)
    conclusions = nbformat.v4.new_markdown_cell("""### Conclusiones de la comparación ejecutada

Resultados externos del escenario que incorpora antigüedad y estado de conservación cuando están disponibles. Los faltantes se tratan dentro del pipeline. Todos los modelos usan las mismas particiones por grupos; MAE y RMSE están expresados en USD/m² cubierto.

| Modelo | MAE ↓ | RMSE ↓ | R² ↑ | MdAPE (%) ↓ |
| --- | ---: | ---: | ---: | ---: |
""" + '\n'.join(rows) + f"""

- **Mejor observado: {best.model} con atributos del edificio**, con MAE de {fmt(best.mae)} USD/m² y R² de {fmt(best.r2, 3)}. Reduce el MAE un **{fmt(improvement, 1)} %** frente a la mediana de comparables ({fmt(baseline.mae)} USD/m²).
- Random Forest queda segundo en este escenario. MLP y KNN mejoran respecto de Ridge, pero no alcanzan el error del HGB en esta captura. La tabla describe el orden observado; no demuestra superioridad universal ni diferencias significativas entre todas las familias.
- Incorporar antigüedad y estado reduce el MAE agregado de las cinco familias frente a sus versiones básicas. La cobertura desigual por fuente impide interpretar esa mejora como garantía para lotes sin esos atributos.
- Los intervalos bootstrap comparan cada modelo con el baseline sobre predicciones externas fijas. No incorporan toda la variabilidad de selección y reentrenamiento. El escenario ganador fue elegido después de observar esta evaluación y necesita confirmación futura.
- La validación temporal del Anexo A corresponde al **HGB operativo**, con otra especificación. Su MAE de 528,7 USD/m² no debe mezclarse con el del ganador del benchmark.

La utilidad del ranking y el ahorro de tiempo requieren una revisión con la inmobiliaria; no se deducen del R² ni del ANOVA. Estas conclusiones son texto estático para que puedan leerse aunque el visor no ejecute widgets.
""", id='conclusiones-modelos-publicas')
    index = next(i for i, cell in enumerate(notebook.cells) if cell.id == 'comparacion')
    notebook.cells.insert(index + 1, conclusions)
    notebook.metadata['publicacion'] = {
        'fuente_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'tipo': 'ejecucion_historica_con_salidas_agregadas',
    }
    nbformat.validate(notebook)
    images = sum('image/png' in output.get('data', {}) for cell in code for output in cell.outputs)
    if images != 9:
        raise ValueError(f'Se esperaban nueve figuras; se encontraron {images}.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(notebook, destination)
    print(f'{destination}: {len(code)} celdas ejecutadas, {images} figuras, conclusiones y anexo.')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/processed/colab-capstone/capstone_integral_entrenado.ipynb')
    parser.add_argument('--destination', type=Path, default=ROOT / 'notebooks/capstone_integral_colab.ipynb')
    args = parser.parse_args()
    publish(args.source, args.destination)


if __name__ == '__main__':
    main()
