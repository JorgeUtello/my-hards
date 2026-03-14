# my-hards 🖱️⌨️

Comparte teclado y mouse entre 2 PCs en la misma red local — como Synergy, pero simple y open source.

## Cómo funciona

- **Server (PC principal):** El PC donde está conectado físicamente el teclado y mouse. Captura los eventos de input y los envía al cliente cuando el cursor cruza el borde de la pantalla.
- **Client (PC remoto):** Recibe los eventos y los reproduce localmente, controlando el cursor y teclado de ese PC.

```
┌──────────────┐  ← cursor sale por    ┌──────────────┐
│              │     el borde derecho   │              │
│   SERVER     │ ─────────────────────► │   CLIENT     │
│  (tu PC)     │                        │  (otro PC)   │
│              │ ◄───────────────────── │              │
│              │  cursor vuelve por     │              │
└──────────────┘     el borde izq.      └──────────────┘
```

## Requisitos

- Python 3.10+
- Ambos PCs en la misma red local
- Windows o Linux

## Instalación

```bash
cd my-hards
pip install -r requirements.txt
```

## Uso rápido

### 1. En el PC principal (Server)

```bash
python main.py
# Seleccionar opción 1 (Server)
```

### 2. En el PC remoto (Client)

```bash
python main.py
# Seleccionar opción 2 (Client)
# Ingresar la IP del server (ej: 192.168.1.100)
```

### O directamente:

```bash
# Server
python server.py

# Client
python client.py 192.168.1.100
```

## Configuración

Genera el archivo de configuración por defecto:

```bash
python main.py
# Seleccionar opción 3
```

Esto crea `config.json`:

```json
{
  "port": 24800,
  "switch_edge": "right",
  "switch_margin": 2,
  "client_screen_width": 1920,
  "client_screen_height": 1080,
  "clipboard_sync": true,
  "heartbeat_interval": 5
}
```

| Parámetro | Descripción |
|-----------|-------------|
| `port` | Puerto TCP para la conexión |
| `switch_edge` | Borde por donde el cursor sale hacia el otro PC: `left`, `right`, `top`, `bottom` |
| `switch_margin` | Píxeles desde el borde para activar el cambio |
| `clipboard_sync` | Sincronizar portapapeles entre PCs |
| `heartbeat_interval` | Segundos entre ping de keep-alive |

## Funcionalidades

- ✅ Compartir mouse (movimiento, clicks, scroll)
- ✅ Compartir teclado (todas las teclas, combinaciones)
- ✅ Cambio automático al cruzar el borde de pantalla
- ✅ Retorno automático al mover el cursor de vuelta
- ✅ Sincronización de portapapeles
- ✅ Heartbeat / detección de desconexión
- ✅ Compatible Windows y Linux

## Firewall

Asegurate de que el puerto 24800 (o el que configures) esté abierto en el firewall del PC server:

**Windows:**
```powershell
netsh advfirewall firewall add rule name="my-hards" dir=in action=allow protocol=TCP localport=24800
```

**Linux:**
```bash
sudo ufw allow 24800/tcp
```

## Estructura del proyecto

```
my-hards/
├── main.py          # Launcher interactivo
├── server.py        # Servidor (PC principal)
├── client.py        # Cliente (PC remoto)
├── protocol.py      # Protocolo de mensajes
├── config.py        # Configuración
├── input_utils.py   # Utilidades de input
├── requirements.txt # Dependencias
└── README.md
```
