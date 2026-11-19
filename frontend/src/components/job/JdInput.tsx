import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

export const JD_FILE_TYPES = ".pdf,.docx,.txt";
const MIN_WORDS = 3; // the API's own minimum

/** Paste or Upload tabs. "Extract requirements" hands the text or file to `onSubmit`. */
export function JdInput({
  pending,
  onSubmit,
}: {
  pending: boolean;
  onSubmit: (input: { title?: string; text: string } | File) => void;
}) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const enoughText = text.trim().split(/\s+/).filter(Boolean).length >= MIN_WORDS;

  return (
    <Tabs defaultValue="paste">
      <TabsList>
        <TabsTrigger value="paste">Paste</TabsTrigger>
        <TabsTrigger value="upload">Upload</TabsTrigger>
      </TabsList>

      <TabsContent value="paste">
        <form
          className="mt-4 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit({ text, ...(title.trim() ? { title: title.trim() } : {}) });
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="jd-title">Job title (optional)</Label>
            <Input
              id="jd-title"
              value={title}
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Read from the description if left empty"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="jd-text">Job description</Label>
            <Textarea
              id="jd-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={16}
              placeholder="Paste the whole job description: responsibilities, requirements, nice-to-haves…"
            />
          </div>
          <Button type="submit" disabled={!enoughText || pending}>
            {pending ? "Extracting…" : "Extract requirements"}
          </Button>
        </form>
      </TabsContent>

      <TabsContent value="upload">
        <form
          className="mt-4 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (file) onSubmit(file);
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="jd-file">Job description file (PDF, DOCX or TXT, up to 5 MB)</Label>
            <Input
              id="jd-file"
              type="file"
              accept={JD_FILE_TYPES}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <Button type="submit" disabled={!file || pending}>
            {pending ? "Extracting…" : "Extract requirements"}
          </Button>
        </form>
      </TabsContent>
    </Tabs>
  );
}
