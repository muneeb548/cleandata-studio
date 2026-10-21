import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button, type ButtonProps } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useWorkspace } from "./WorkspaceContext";

/**
 * Deletes the uploaded file, the cleaned data and the history from the server right away,
 * instead of waiting for the inactivity timeout. Asks first, because it cannot be undone.
 */
export function DeleteDataButton({ label = "Delete my data now", ...props }: ButtonProps & { label?: string }) {
  const { deleteData, setTab } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const confirm = async () => {
    setBusy(true);
    const done = await deleteData();
    setBusy(false);
    if (done) setOpen(false);
  };

  return (
    <>
      <Button variant="danger-outline" size="sm" onClick={() => setOpen(true)} {...props}>
        <Trash2 /> {label}
      </Button>
      <Dialog
        open={open}
        onClose={() => !busy && setOpen(false)}
        title="Delete your data from the server?"
        description="The uploaded file, the cleaned data, the cleaning history and the steps saved in this browser are removed now. Download your cleaned file first if you still need it. This cannot be undone."
        footer={
          <>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => {
                setOpen(false);
                setTab("export");
              }}
            >
              Download first
            </Button>
            <Button variant="danger" loading={busy} onClick={() => void confirm()}>
              Delete now
            </Button>
          </>
        }
      />
    </>
  );
}
