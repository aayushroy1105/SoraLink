
# SoraLink — Local Network Setup

## 1. Purpose

This guide explains how to run SoraLink on one host device and connect passenger and crew browsers over a local Wi-Fi network without requiring internet access during the demonstration.

## 2. Architecture

- One host runs Flask, SQLite, local Whisper, and the intent classifier.
- Passenger devices access the passenger interface through their browsers.
- The crew device accesses the crew interface through its browser.
- REST and Socket.IO traffic stays on the local network.
- All required Python packages, model weights, and browser assets must be available locally before internet access is disabled.

## 3. Host Preparation

Before the offline demonstration:

1. Install the agreed Python version.
2. Create and activate a virtual environment.
3. Install the tested dependencies from `requirements.txt`.
4. Initialize SQLite using the documented setup procedure.
5. Seed demo passenger invitations and crew credentials.
6. Download and test the selected local AI model weights.
7. Verify that required audio-decoding tools are installed.
8. Start Flask and test the passenger and crew pages locally.

Do not download packages or model weights during the offline demonstration.

## 4. Local Network

1. Connect the host, passenger device, and crew device to the same Wi-Fi network or host hotspot.
2. Find the host's local IP address.
3. Configure Flask to listen on the intended network interface.
4. Open the application from a second device using the host's local address and configured port.
5. Verify that the passenger and crew interfaces load.

Example address format:

`http://HOST_LOCAL_IP:5000`

Replace `HOST_LOCAL_IP` with the actual host address. This example is for initial network testing only.

## 5. HTTPS and Microphone Access

Mobile browsers generally require a secure context for microphone access, with localhost treated specially.

Before relying on voice recording over the local network:

1. Configure a trusted HTTPS certificate for the local hostname.
2. Install and trust the required certificate authority on the physical test devices, if necessary.
3. Confirm microphone permission in each browser.
4. Test the actual recording MIME type returned by the browser.
5. Confirm the server can decode the recorded format.

If HTTPS or microphone permissions are unavailable, retain the visual and typed request workflows. Use a pre-recorded audio upload for controlled voice-pipeline testing when appropriate.

Do not assume that visiting an HTTP address using a local IP automatically permits microphone access.

## 6. Offline Model Preparation

Before disabling internet access:

1. Download the selected Whisper model.
2. Download any required SetFit and sentence-transformer model weights.
3. Confirm all dependencies are installed.
4. Run a transcription test.
5. Run an intent-classification test.
6. Verify that the model code loads cached weights without attempting a network download.

Record the tested model versions and hardware used.

## 7. Startup and Verification

1. Activate the virtual environment.
2. Start the application using the team's documented command.
3. Confirm that the server is listening on the expected interface and port.
4. Open the passenger page.
5. Open the crew page on another device.
6. Authenticate both roles.
7. Submit a visual request and confirm that it appears in the crew queue.
8. Acknowledge and complete the request.
9. Refresh the passenger page and confirm that its state is recovered.
10. Broadcast a PA card and verify persistence after refresh.

## 8. WAN-Disconnected Test

After preparing all dependencies and assets:

1. Disable internet/WAN connectivity while keeping the local network active.
2. Restart the application.
3. Repeat the complete visual request workflow.
4. Test crew notifications and state recovery.
5. Test PA broadcast persistence.
6. Test local AI only if all required model files and dependencies are available.

Record actual results. Do not claim offline readiness until the workflow has been tested with WAN access disabled.

## 9. Troubleshooting

### A device cannot open the application
- Confirm both devices are on the same local network.
- Verify the host IP and port.
- Check the server bind address and firewall rules.
- Check that the host has not changed IP address.

### The microphone does not work
- Verify HTTPS and certificate trust.
- Check browser microphone permissions.
- Inspect the browser-supported recording MIME type.
- Use the visual or typed fallback if recording remains unavailable.

### Socket.IO notifications do not arrive
- Confirm that the device can reach the host.
- Check authentication and room assignment.
- Inspect server and browser logs.
- Confirm REST state recovery works after reconnecting.

### Voice inference fails offline
- Confirm that model weights exist locally.
- Check installed audio-decoding dependencies.
- Verify that the selected runtime supports the host hardware.
- Ensure the application does not attempt to download missing model files.

## 10. Demo Safety

Use only synthetic passenger data and demo credentials.

Do not commit secrets, local session databases, raw audio recordings, or downloaded model weights to the GitHub repository.

The hackathon prototype is not certified airline software and must not be deployed on a real aircraft without the necessary engineering, security, accessibility, network, and airline approvals.
