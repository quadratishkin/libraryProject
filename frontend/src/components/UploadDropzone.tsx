import { DragEvent, useRef, useState } from "react";

interface Props {
  onUpload: (files: File[]) => Promise<void> | void;
}

export default function UploadDropzone({ onUpload }: Props) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    if (!event.dataTransfer.files.length) return;
    onUpload(Array.from(event.dataTransfer.files));
  };

  return (
    <div
      className={`dropzone ${isDragging ? "dragging" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".fb2"
        multiple
        style={{ display: "none" }}
        onChange={(e) => {
          if (!e.target.files?.length) return;
          onUpload(Array.from(e.target.files));
          e.target.value = "";
        }}
      />
      <p>Перетащите FB2-файлы сюда или нажмите для выбора</p>
      <small>Максимум 50 МБ на файл</small>
    </div>
  );
}
