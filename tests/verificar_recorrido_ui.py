import argparse
import json
import re
from pathlib import Path
import socket
import sys
import tempfile
import threading

import uvicorn
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from precio_entorno.api import create_app


def contraste(foreground, background):
    def luz(color):
        if color.startswith("#"):
            values = [int(color[i:i + 2], 16) / 255 for i in [1, 3, 5]]
        else:
            values = [float(n) / 255 for n in re.findall(r"[\d.]+", color)[:3]]
        rgb = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
        return sum(v * weight for v, weight in zip(rgb, [0.2126, 0.7152, 0.0722]))
    a, b = sorted([luz(foreground), luz(background)])
    return (b + 0.05) / (a + 0.05)


def borrar_busquedas(context, url, mode):
    """Borra las búsquedas de compra guardadas en un modo, para empezar el recorrido limpio."""
    saved = context.request.get(f"{url}/api/busquedas?modo={mode}&operacion=venta").json()
    for search in saved["busquedas"]:
        context.request.delete(f"{url}/api/busquedas/{search['id']}?modo={mode}&operacion=venta")


def verificar(browser, url, output, name, width, height):
    context = browser.new_context(viewport={"width": width, "height": height},
                                  device_scale_factor=2 if name == "zoom200" else 1,
                                  reduced_motion="no-preference" if name == "escritorio" else "reduce")
    context.add_init_script("localStorage.setItem('precio-entorno-filtros', JSON.stringify({modo:'demo'}))")
    for mode in ["demo", "real"]:
        borrar_busquedas(context, url, mode)
    page = context.new_page()
    page.set_default_timeout(12000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    posts = []
    page.on("request", lambda request: posts.append(request.post_data_json)
            if request.method == "POST" and "/api/busquedas" in request.url else None)
    page.goto(url, wait_until="domcontentloaded")
    first = page.locator(".barrios .fila").first
    expect(first).to_be_visible()
    style = page.evaluate("""() => {
      const root = getComputedStyle(document.documentElement);
      const token = n => root.getPropertyValue(n).trim();
      return {body:getComputedStyle(document.body).fontSize,
        text:token('--asfalto'), secondary:token('--asfalto-suave'), surface:token('--papel'),
        primary:token('--jacaranda-oscuro'), border:token('--borde-control'),
        error:token('--alerta'), errorBg:token('--error-fondo'),
        success:token('--platano'), successBg:token('--exito-fondo')};
    }""")
    assert style["body"] == "16px"
    ratios = {"texto": contraste(style["text"], style["surface"]),
              "ayudas": contraste(style["secondary"], style["surface"]),
              "accion": contraste(style["surface"], style["primary"]),
              "error": contraste(style["error"], style["errorBg"]),
              "confirmacion": contraste(style["success"], style["successBg"]),
              "borde": contraste(style["border"], style["surface"])}
    assert all(value >= (3 if key == "borde" else 4.5) for key, value in ratios.items()), ratios
    mobile = width <= 820
    if mobile:
        toggle = page.locator("#alternar-filtros")
        toggle.click()
        expect(page.locator("#filtros")).to_be_visible()
        for selector in ["#presupuesto", "#superficie", "#ambientes", "#abrir-importa"]:
            box = page.locator(selector).bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1
        page.locator("#abrir-importa").click()
        expect(page.locator("#preferencias")).to_be_visible()
        page.screenshot(path=str(output / f"{name}-filtros.png"))
        page.keyboard.press("Escape")
        page.keyboard.press("Escape")
        expect(toggle).to_have_attribute("aria-expanded", "false")
        expect(toggle).to_be_focused()
        if page.locator("#panel-asa").get_attribute("aria-expanded") != "true":
            page.locator("#panel-asa").click()
    if mobile:
        page.locator("#alternar-filtros").click()
    compra = page.locator('[data-operacion="venta"]')
    alquiler = page.locator('[data-operacion="alquiler"]')
    compra.focus()
    with page.expect_response(lambda r: "/api/barrios?" in r.url and "alquiler" in r.url):
        page.keyboard.press("ArrowRight")
    expect(alquiler).to_have_attribute("aria-checked", "true")
    expect(compra).to_have_attribute("tabindex", "-1")
    expect(page.locator("#presupuesto")).to_have_attribute("aria-label", "Presupuesto máximo por mes en ARS")
    with page.expect_response(lambda r: "/api/barrios?" in r.url and "venta" in r.url):
        page.keyboard.press("Home")
    expect(compra).to_have_attribute("aria-checked", "true")
    expect(page.locator("#estado-resultados")).to_contain_text("compra, datos de ejemplo")
    if mobile:
        page.locator("#alternar-filtros").click()
    assert page.locator("#contenido").evaluate("e=>e.scrollWidth<=e.clientWidth+1")
    page.locator("#orden-barrios").select_option("precio")
    prices = page.locator(".fila-mediana").all_text_contents()
    assert prices and "100.000" in prices[0]
    for i in range(3):
        page.locator("[data-comparar]").nth(i).check()
    expect(page.locator("#abrir-comparacion")).to_be_enabled()
    page.locator("#contenido").evaluate("e=>e.scrollTop=e.scrollHeight")
    expect(page.locator("#comparacion-pie button")).to_be_visible()
    page.locator("#comparacion-pie button").click()
    comparison = page.locator("#dialogo-comparacion")
    expect(comparison).to_be_visible()
    expect(comparison).to_contain_text("Avisos ficticios de ejemplo")
    expect(comparison.locator("tbody th")).to_contain_text(["Avisos que encajan", "Mediana publicada", "Subte", "Plazas y parques", "Seguir con este barrio"])
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    page.screenshot(path=str(output / f"{name}-comparacion.png"))
    page.locator("#dialogo-comparacion [data-cerrar]").click()
    expect(page.locator("#comparacion-pie button")).to_be_focused()
    page.locator("[data-abrir-importa]").first.click()
    expect(page.locator("#preferencias")).to_be_visible()
    page.locator('#preferencias [value="verdes"]').uncheck()
    page.locator('#preferencias [value="ruido"]').check()
    page.keyboard.press("Escape")
    if mobile:
        page.keyboard.press("Escape")
    page.locator("#abrir-comparacion").click()
    expect(comparison.locator("tbody th")).to_contain_text(["Avisos que encajan", "Mediana publicada", "Subte", "Ruido", "Seguir con este barrio"])
    assert "Plazas y parques" not in comparison.locator("tbody th").all_text_contents()
    page.locator("[data-elegir-comparado]").first.click()
    expect(comparison).not_to_be_visible()
    expect(page.locator("#comparacion-pie")).not_to_be_visible()
    page.locator("#volver").click()
    page.locator("#limpiar-comparacion").click()
    expect(page.locator("#abrir-comparacion")).to_be_disabled()
    assert page.locator("[data-comparar]:checked").count() == 0
    expect(page.locator("#comparacion-pie")).not_to_be_visible()
    page.screenshot(path=str(output / f"{name}-barrios.png"))
    barrio = first.get_attribute("data-barrio")
    first.click()
    expect(page.locator("#titulo-vista")).to_have_text(barrio)
    page.wait_for_function("estado.avisos.length > 0")
    page.go_back()
    expect(page.locator(".titulo-lista")).to_be_visible()
    expect(first).to_be_focused()
    page.go_forward()
    expect(page.locator("#titulo-vista")).to_have_text(barrio)
    page.wait_for_function("estado.avisos.length > 0")
    if mobile and page.locator("#panel-asa").get_attribute("aria-expanded") == "true":
        page.locator("#panel-asa").click()
    assert page.locator('#capas [data-capa]').count() == 16
    noise = page.locator('#capas [data-capa="ruido"]')
    if noise.get_attribute("aria-pressed") != "true":
        noise.click()
    page.locator('#capas [data-capa="escuelas"]').click()
    page.locator('#capas [data-capa="colectivos"]').click()
    expect(page.locator('#capas [data-capa="colectivos"]')).to_have_attribute('aria-pressed','true')
    page.locator('#capas [data-capa="colectivos"]').click()
    page.screenshot(path=str(output / f"{name}-capas-visibles.png"))
    page.locator("#abrir-mapa").click()
    map_dialog = page.locator("#dialogo-mapa")
    expect(map_dialog).to_be_visible()
    expect(page.locator('[data-ruido="diurno"]')).to_be_visible()
    page.locator('[data-ruido="diurno"]').focus()
    page.keyboard.press("ArrowRight")
    expect(page.locator('[data-ruido="nocturno"]')).to_have_attribute("aria-checked", "true")
    expect(page.locator("#leyenda")).to_contain_text("65 dBA")
    expect(page.locator('[data-ruido="nocturno"]')).to_be_focused()
    page.locator('[data-control="nivel"]').focus()
    page.locator('[data-control="nivel"]').select_option("secundario")
    expect(page.locator("#leyenda")).to_contain_text("secundario")
    expect(page.locator('[data-control="nivel"]')).to_be_focused()
    page.locator("#apagar-capas").click()
    expect(page.locator("#estado-capas")).to_contain_text("0 capas activadas")
    page.locator("#capas-preferidas").click()
    expect(page.locator("#estado-capas")).to_contain_text("2 capas activadas")
    page.screenshot(path=str(output / f"{name}-capas.png"))
    page.locator("#dialogo-mapa [data-cerrar]").click()
    expect(page.locator("#abrir-mapa")).to_be_focused()
    page.locator("#centrar-mapa").click()
    page.screenshot(path=str(output / f"{name}-mapa.png"))
    if mobile:
        page.locator("#panel-asa").click()
    page.locator("#contenido").evaluate("e=>e.scrollTop=e.scrollHeight")
    tabs = page.locator(".pestanas").bounding_box()
    panel = page.locator("#contenido").bounding_box()
    assert tabs["y"] >= panel["y"] - 1 and tabs["y"] + tabs["height"] < panel["y"] + panel["height"]
    page.locator("#pestana-entorno").focus()
    page.keyboard.press("ArrowRight")
    expect(page.locator("#pestana-avisos")).to_be_focused()
    expect(page.locator("#panel-avisos")).to_be_visible()
    assert page.locator("#contenido").evaluate("e=>e.scrollWidth<=e.clientWidth+1")
    table = page.locator(".tabla-desplazable")
    if table.evaluate("e=>e.scrollWidth>e.clientWidth"):
        table.focus()
        page.keyboard.press("ArrowRight")
    page.screenshot(path=str(output / f"{name}-avisos.png"))
    page.locator("#pestana-avisos").focus()
    page.keyboard.press("End")
    expect(page.locator("#panel-alerta")).to_be_visible()
    page.go_back()
    expect(page.locator(".titulo-lista")).to_be_visible()
    page.go_forward()
    expect(page.locator("#pestana-alerta")).to_have_attribute("aria-selected", "true")
    expect(page.locator("#panel-alerta")).to_contain_text("no envía correos")
    page.locator("#crear-alerta").focus()
    controls = page.evaluate("""() => ['#crear-alerta','#presupuesto','#orden-barrios'].map(s=>document.querySelector(s)).filter(e=>e&&e.getClientRects().length).map(e=>({
      font:getComputedStyle(e).fontSize, radius:getComputedStyle(e.closest('.campo')||e).borderRadius,
      height:(e.closest('.campo')||e).getBoundingClientRect().height}))""")
    assert all(c["font"] == "16px" and c["radius"] == "12px" and c["height"] >= 44 for c in controls), controls
    page.keyboard.press("Enter")
    expect(page.locator("#estado-alerta")).to_contain_text("Búsqueda guardada")
    assert len(posts) == 1 and posts[0]["barrio"] == barrio
    page.evaluate("renderPanel()")
    expect(page.locator("#estado-alerta")).to_contain_text("Búsqueda guardada")
    page.screenshot(path=str(output / f"{name}-guardada.png"))
    page.locator("[data-ver-alertas]").click()
    expect(page.locator("#dialogo-alertas")).to_be_visible()
    expect(page.locator("#alertas-contenido")).to_contain_text(barrio)
    expect(page.locator("#alertas-contenido")).to_contain_text("Todavía no entró ningún aviso nuevo")
    page.screenshot(path=str(output / f"{name}-mis-alertas.png"))
    page.locator("#dialogo-alertas [data-cerrar]").click()
    expect(page.locator("[data-ver-alertas]")).to_be_focused()
    zoom = page.locator(".maplibregl-ctrl-zoom-in")
    if not mobile and zoom.count():
        rect = zoom.bounding_box()
        assert page.evaluate("([x,y])=>Boolean(document.elementFromPoint(x,y)?.closest('.maplibregl-ctrl-zoom-in'))",
                             [rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2])

    # El servidor usa bases temporales y el envío por correo está desactivado.
    page.locator('[data-modo="real"]').click()
    page.wait_for_function("estado.modo==='real' && estado.barrios.every(b=>b.avisos===0)")
    page.locator("#volver").click()
    page.locator('[data-barrio="Almagro"]').click()
    page.locator("#pestana-alerta").click()
    email = page.locator("#mail-alerta")
    email.fill("invalido")
    page.locator("#consentimiento-alerta").check()
    page.locator("#crear-alerta").click()
    expect(email).to_have_attribute("aria-invalid", "true")
    expect(email).to_be_focused()
    assert len(posts) == 1
    email.fill("prueba@example.com")
    page.evaluate("renderPanel()")
    expect(email).to_have_value("prueba@example.com")
    expect(page.locator("#consentimiento-alerta")).to_be_checked()
    expect(email).to_be_focused()
    # Una falla del servidor conserva el borrador y permite reintentar.
    def fail_once(route):
        if route.request.method == "POST":
            route.fulfill(status=503, content_type="application/json", body='{"detail":"Servicio no disponible"}')
        else:
            route.continue_()
    page.route("**/api/busquedas?*", fail_once)
    page.locator("#crear-alerta").click()
    expect(page.locator("#estado-alerta")).to_contain_text("No se creó la alerta")
    page.unroute("**/api/busquedas?*", fail_once)
    expect(email).to_have_value("prueba@example.com")
    expect(page.locator("#crear-alerta")).to_be_enabled()
    # Dos submits consecutivos no duplican el pedido pendiente.
    page.evaluate("document.querySelector('#form-alerta').requestSubmit(); document.querySelector('#form-alerta').requestSubmit()")
    expect(page.locator("#estado-alerta")).to_contain_text("No se activó el aviso por correo")
    assert len(posts) == 3
    assert not errors, errors
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    page.screenshot(path=str(output / f"{name}-correo-no-disponible.png"))
    context.close()
    return {"pantalla": name, "ancho": width, "alto": height, "resultado": "OK", "errores_js": errors,
            "contraste": {k: round(v, 2) for k, v in ratios.items()}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ui-audit"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="luga-ui-") as temp:
        app = create_app(demo_path=Path(temp) / "demo.sqlite3", real_path=Path(temp) / "real.sqlite3", subscriptions_url=None)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        worker = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        worker.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, **({"executable_path": str(args.browser)} if args.browser else {}))
                results = []
                for name, width, height in [("escritorio", 1440, 900), ("celular", 375, 812),
                                            ("celular-chico", 320, 740), ("tablet", 768, 1024),
                                            ("horizontal", 844, 390), ("zoom200", 720, 450)]:
                    results.append(verificar(browser, f"http://127.0.0.1:{port}", args.output, name, width, height))
                    print(name, "OK", flush=True)
                browser.close()
                (args.output / "verificacion.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            server.should_exit = True
            worker.join(timeout=10)
            sock.close()


if __name__ == "__main__":
    main()
