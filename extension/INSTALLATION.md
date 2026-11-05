# Installing Fill with JobPilot

The extension is not on the Chrome Web Store (publishing there needs the owner's approval and developer account), so
you install it unpacked. Works in Google Chrome, Microsoft Edge, Brave and other Chromium browsers (version 116+).

## 1. Get the extension folder

Either:
- use the `extension/` folder of this repository, or
- unzip `fill-with-jobpilot-1.0.0.zip` (from `npm run package` or the project owner) into a folder you will keep.
  Chrome loads it from that folder every time, so don't delete it.

## 2. Load it

1. Open `chrome://extensions` (Edge: `edge://extensions`).
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and choose the folder that contains `manifest.json`.
4. Pin **Fill with JobPilot** from the puzzle-piece menu so the icon is always visible.

The extension ID must be `ehpfmhhbnijflgagkpdbhiakldmgedgp`. The JobPilot server only accepts requests from that ID.

## 3. Connect it to your JobPilot account

1. In JobPilot open **Settings → Browser extension** and click **Create connection code**.
2. Click the extension icon, type the 8-character code (for example `AB12-CD34`) and click **Connect** within
   5 minutes. The code works once.
3. The browser now appears under **Connected browsers**. It stays connected for 90 days (renewed automatically while
   you use it) or until you click **Disconnect** there or in the extension's Settings.

You never type your JobPilot password into the extension.

## 4. Use it

Open a job from JobPilot, go to the application form, click the extension icon and follow the steps (see
[README.md](README.md)). Add any missing profile details it lists (Settings → Resume & profile or Verified answers).

## Updating

Replace the folder's contents with the new version and click the reload icon on the extension's card in
`chrome://extensions`. Your connection is kept.

## Removing

Click **Disconnect** in JobPilot Settings → Browser extension (this revokes the credential on the server), then
**Remove** on `chrome://extensions`. Removing the extension deletes its local data.

## Troubleshooting

| Message | What to do |
|---|---|
| "JobPilot is not reachable right now" | The JobPilot server is offline, or its address changed and the web app has not republished it yet. Try again in a few minutes. |
| "This browser was disconnected" | The connection was revoked or expired: create a new code and connect again. |
| "Not an application page" | The page is not a Greenhouse, Lever or Ashby form (for example an employer's own careers site). Use JobPilot's **Open Greenhouse application form** where it is offered, or apply manually. |
| "No application form is visible yet" | Click Apply on the job page first. |
| Resume not attached | Use **Download** and attach the file yourself. Some forms only accept files you choose. |
