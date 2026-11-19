import { Upload } from "lucide-react";
import { useDropzone } from "react-dropzone";

import { MAX_FILE_MB, MAX_FILES, RESUME_TYPES } from "@/lib/files";
import { cn } from "@/lib/utils";

/**
 * Drag and drop, or click to choose. Every dropped file is passed on, including ones of the
 * wrong type: the page checks them all and says why a file can't be uploaded.
 */
export function FileDropzone({
  onFiles,
  disabled,
}: {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: RESUME_TYPES, // filters the file picker
    multiple: true,
    disabled,
    onDrop: (accepted, rejections) => onFiles([...accepted, ...rejections.map((r) => r.file)]),
  });
  return (
    <div
      {...getRootProps({
        "aria-label": "Choose resume files",
        className: cn(
          "flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-10 text-center transition-colors",
          isDragActive ? "border-primary bg-accent" : "hover:bg-accent/50",
          disabled && "pointer-events-none opacity-50",
        ),
      })}
    >
      <input {...getInputProps()} />
      <Upload className="size-8 text-muted-foreground" aria-hidden />
      <p className="font-medium">
        {isDragActive ? "Drop the resumes here" : "Drag resumes here, or click to choose"}
      </p>
      <p className="text-sm text-muted-foreground">
        PDF or DOCX · up to {MAX_FILE_MB} MB each · up to {MAX_FILES} files
      </p>
    </div>
  );
}
