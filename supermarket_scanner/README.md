# ShelfScan: supermarket barcode scanner

1. `pip install -r requirements.txt`
2. Install the zbar library (needed by pyzbar):
   - Windows: bundled with the pyzbar wheel
   - macOS: `brew install zbar`
   - Ubuntu/Debian: `sudo apt install libzbar0`
3. `python app.py`, then open http://localhost:5000

Change the currency symbol with `CURRENCY` in app.py. Camera index is set in scanner.py (`Scanner(camera_index=0)`).
Without a camera you can type barcodes or upload a barcode photo. products.db is created on first run with 5 sample products.
