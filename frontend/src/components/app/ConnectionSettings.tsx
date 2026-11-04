import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useConnection } from "@/contexts/ConnectionContext";
import { normalizeBaseUrl, storedBaseUrl } from "@/lib/config";

const sourceLabel = {
  query: "from the link you opened",
  saved: "saved in this browser",
  published: "published by the portal owner",
  build: "built into this site",
  none: "not set",
} as const;

export function ConnectionSettingsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const c = useConnection();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setValue(storedBaseUrl() ?? c.baseUrl ?? "");
  }, [open, c.baseUrl]);

  const save = async (url: string | null) => {
    if (url && !normalizeBaseUrl(url)) {
      toast.error("Enter a full URL such as https://example.ngrok-free.app");
      return;
    }
    setBusy(true);
    const ok = await c.setBaseUrl(url);
    setBusy(false);
    if (ok) {
      toast.success("Connected to the backend");
      onOpenChange(false);
    } else {
      toast.error("Saved, but the backend at that address is not responding yet");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Backend address</DialogTitle>
          <DialogDescription>
            The portal talks to a backend running on the owner's machine (usually an https ngrok address).
            Current: <span className="font-medium">{c.baseUrl ?? "none"}</span> ({sourceLabel[c.baseUrlSource]}).
          </DialogDescription>
        </DialogHeader>
        <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder="https://your-tunnel.ngrok-free.app" aria-label="Backend URL" />
        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => save(null)} disabled={busy}>Use published address</Button>
          <Button onClick={() => save(value)} disabled={busy || !value.trim()}>Save & test</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
