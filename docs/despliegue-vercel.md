# Despliegue en Vercel

La interfaz web también corre en Vercel, en `https://precio-entorno-caba.vercel.app`, con los **datos reales y acceso público** desde el 17/11/2026. Hasta esa fecha estuvo protegida con Vercel Authentication. La persona dueña del proyecto confirmó que las fuentes del catálogo (inmobiliarias y portales, incluidos Zonaprop, Clarín y Mob) autorizan mostrar sus avisos al público. Si una fuente retira ese permiso, hay que sacar sus avisos de las bases antes del siguiente despliegue o volver a activar la protección.

## Cómo está armado

- **Entrada:** `precio_entorno/vercel_app.py`, declarada en `[tool.vercel] entrypoint`. La raíz del repositorio tiene `app.py`, que es la app de Streamlit, y no se despliega.
- **Disco de solo lectura:** en Vercel solo `/tmp` admite escritura. Al arrancar, cada instancia copia las bases reales a `/tmp/precio-entorno/` y crea ahí la demo. **Una búsqueda guardada en Vercel dura lo que dura la instancia.** La base que cuenta sigue siendo la local, que actualiza `actualizar.py`. El alta con mail se manda a Make como en local, así que el aviso por correo no depende de esa copia.
- **Carpeta desplegada:** la arma `scripts/preparar_vercel.py` en `.vercel-build/` (ignorada por Git):
  - código de `HEAD` (`git archive`), no del árbol de trabajo, para no publicar cambios sin confirmar;
  - bases reales, capas del mapa (incluidos los garajes comerciales), catálogo de cocheras, CSV anuales del Mapa del Delito y radar (unos 60 MB);
  - `pyproject.toml` con solo FastAPI, NumPy, Matplotlib y httpx (lo usan «Dónde comer» y la interpretación de preferencias), `.python-version` y `vercel.json`.
  No se copian `.env`, crudos de captura ni la app de Streamlit.

## Desplegar o actualizar los datos

```bash
python scripts/preparar_vercel.py --desplegar
```

Sin `--desplegar`, el script solo arma la carpeta. La carpeta queda vinculada al proyecto en `.vercel-build/.vercel/`, y el script la conserva. Para que Vercel muestre avisos nuevos hay que volver a correr el comando después de `actualizar.py`.

**No desplegar con `vercel deploy` a secas desde `.vercel-build/`.** La carpeta está dentro del repositorio y la CLI adjunta el último commit. Vercel bloqueó un despliegue así («el autor del commit no tiene permiso para crear despliegues en este proyecto»). `--desplegar` corre la CLI sin acceso a Git.

## Protección

- Desde el 17/11/2026 el proyecto no tiene `ssoProtection`: la URL de producción y las generadas abren sin sesión. Se desactivó con `vercel project protection disable precio-entorno-caba --sso`.
- Para volver a hacerla privada: `vercel project protection enable precio-entorno-caba --sso` y comprobar, sin sesión:

  ```bash
  curl -s -o /dev/null -w "%{http_code}\n" https://precio-entorno-caba.vercel.app/api/estado
  ```

  Con la protección activa tiene que responder `302` (redirección al inicio de sesión de Vercel); pública, `200`.
- Con la web abierta, cualquiera puede guardar una búsqueda con aviso por correo. Cada alta llega al escenario de Make, que en el plan gratuito tiene un tope de operaciones.
- **Lección del primer despliegue (13/11/2026):** la protección estándar de un proyecto nuevo cubre las URL generadas, pero no `precio-entorno-caba.vercel.app`. Además, el primer despliegue de un proyecto va directo a producción. Durante unos minutos esa URL respondió sin sesión, hasta que se pasó la protección a `all`. En un proyecto nuevo, activar la protección para todos los despliegues **antes** del primer despliegue.

## Secretos

- `MAKE_BUSQUEDAS_WEBHOOK_URL` se carga como variable sensible del entorno de producción, con `vercel env add MAKE_BUSQUEDAS_WEBHOOK_URL --environment production --sensitive` (el valor lo pega la persona dueña de la cuenta). Hace falta volver a desplegar para que tome efecto.
- Nunca se suben `.env` ni `.env.local`. Si la CLI crea un `.env.local` en `.vercel-build/` (token OIDC de desarrollo), el script lo borra en la siguiente preparación.
