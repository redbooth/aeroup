# AeroUP

AeroUP is service which uses the AeroFS API to allow 3rd-party file uploads,
even if the AeroFS Appliance sits behind the firewall.

## Getting Started

Register an app in your AeroFS Appliance, by visiting the appliance settings
page. For development, pick any name (it doesn't matter) and use the redirect
URI `http://127.0.0.1:5000/login_complete`.

Download the app config as a JSON blob (also on the appliance settings page)
and place it in the same folder as this README.md.

Then:

```bash
pip install -r requirements.txt
./run.py debug
```

Visit 127.0.0.1:5000 in your browser, and enjoy.
