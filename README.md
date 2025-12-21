# GPS Reader for Raspberry Pi 5

Read GPS data from your Android phone over WiFi LAN using GPSd Forwarder.

## Prerequisites

### On Your Android Phone:
1. Install **GPSd Forwarder** from Google Play Store
2. Open the app and configure:
   - Enable "Start on Boot" (optional)
   - Note the port number (default: 2947)
3. Start the GPS forwarding service
4. Find your phone's IP address (Settings → About Phone → Status → IP address)
5. Make sure your phone and Raspberry Pi are on the same WiFi network

### On Your Raspberry Pi 5:
- Python 3.7 or higher
- Internet connection (for initial setup)

## Installation

1. Clone or download this project to your Raspberry Pi

2. Run the setup script:
```bash
chmod +x setup.sh
./setup.sh
```

This will:
- Create a Python virtual environment
- Install required dependencies (gps3 library)

## Usage

### Activate the Virtual Environment

Before running the application, activate the virtual environment:
```bash
source venv/bin/activate
```

### Basic Usage

Run the GPS reader with your phone's IP address:
```bash
python gps_client.py --host 192.168.1.50
```

Replace `192.168.1.50` with your phone's actual IP address.

### Command Line Options

```bash
python gps_client.py [OPTIONS]

Options:
  --host HOST           IP address of phone running GPSd Forwarder
                        (default: 192.168.1.100)
  
  --port PORT           GPSd port (default: 2947)
  
  --interval SECONDS    Update interval in seconds (default: 1.0)
  
  --json                Output as JSON instead of formatted display
```

### Examples

**Basic usage with custom IP:**
```bash
python gps_client.py --host 192.168.1.50
```

**Custom port:**
```bash
python gps_client.py --host 192.168.1.50 --port 2947
```

**Faster updates (0.5 seconds):**
```bash
python gps_client.py --host 192.168.1.50 --interval 0.5
```

**JSON output for logging or processing:**
```bash
python gps_client.py --host 192.168.1.50 --json > gps_log.json
```

**Custom callback (for your own processing):**
Edit the `gps_client.py` file and modify the `run_continuous` method to process data as needed.

## Displayed Data

The application displays:
- **GPS Fix Status**: No fix, 2D fix, or 3D fix
- **Position**: Latitude, Longitude, Altitude
- **Satellites**: Number of satellites used
- **Time**: GPS time
- **Movement**: Speed, Track (direction), Climb rate
- **Accuracy**: Position error estimates (EPX, EPY, EPV)

## Troubleshooting

### Can't connect to phone:

1. **Check IP address**: Make sure you have the correct IP address
   ```bash
   # Try to ping your phone
   ping 192.168.1.50
   ```

2. **Check port**: Verify the port in GPSd Forwarder app (default is 2947)

3. **Firewall**: Make sure your phone's firewall allows connections on port 2947

4. **Same network**: Ensure both devices are on the same WiFi network

5. **GPSd Forwarder running**: Check that the service is started in the app

### No GPS fix:

1. Make sure your phone has a clear view of the sky
2. Wait a few minutes for initial satellite lock
3. Check that Location Services are enabled on your phone
4. Verify GPS is working in Google Maps or another GPS app

### Virtual environment issues:

If you need to recreate the virtual environment:
```bash
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Deactivate Virtual Environment

When you're done:
```bash
deactivate
```

## Running on Startup (Optional)

To run the GPS reader automatically on boot:

1. Create a systemd service file:
```bash
sudo nano /etc/systemd/system/gps-reader.service
```

2. Add the following content (adjust paths and IP):
```ini
[Unit]
Description=GPS Reader Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/gps_reader
ExecStart=/home/pi/gps_reader/venv/bin/python /home/pi/gps_reader/gps_client.py --host 192.168.1.50
Restart=always

[Install]
WantedBy=multi-user.target
```

3. Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable gps-reader.service
sudo systemctl start gps-reader.service
```

4. Check status:
```bash
sudo systemctl status gps-reader.service
```

## License

Free to use and modify for your needs.

## Notes

- The `gps3` library provides a simple interface to GPSd
- GPS accuracy depends on your phone's GPS hardware and satellite visibility
- The application will continue retrying if connection is lost
- Press Ctrl+C to stop the application

## Support

For issues with:
- **GPSd Forwarder**: Check the app's documentation or Google Play reviews
- **This application**: Check the error messages and troubleshooting section above
- **GPS accuracy**: This depends on your phone's hardware and environment
