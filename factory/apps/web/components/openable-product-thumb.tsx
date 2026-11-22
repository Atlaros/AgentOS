"use client";

import { useState } from "react";

import { ImageViewer } from "./image-viewer";
import { ProductThumb, type ProductThumbProps, resolveProductThumbSrc } from "./product-thumb";

export type OpenableProductThumbProps = ProductThumbProps & {
  sources?: string[];
};

export function OpenableProductThumb({ sources, ...thumb }: OpenableProductThumbProps) {
  const [open, setOpen] = useState(false);
  const resolved = resolveProductThumbSrc(thumb.thumbUrl, thumb.imageUrl);
  const gallery =
    sources && sources.length > 0
      ? sources
      : resolved
        ? [resolved]
        : [];

  return (
    <>
      <ProductThumb
        {...thumb}
        onOpen={gallery.length > 0 ? () => setOpen(true) : undefined}
      />
      <ImageViewer
        open={open}
        onClose={() => setOpen(false)}
        sources={gallery}
        alt={thumb.name}
        title={thumb.name}
      />
    </>
  );
}
