/**
 * `html2pdf.js` ships no type declarations, and this is the whole surface the
 * report uses. Kept deliberately narrow: a `declare module "html2pdf.js"` with
 * `any` would compile just as well and would let a typo in an option key
 * survive to runtime, where the failure mode is a blank PDF.
 */
declare module "html2pdf.js" {
  interface Html2PdfOptions {
    margin?: number | [number, number, number, number];
    filename?: string;
    image?: { type?: "jpeg" | "png" | "webp"; quality?: number };
    html2canvas?: {
      scale?: number;
      useCORS?: boolean;
      allowTaint?: boolean;
      backgroundColor?: string | null;
      logging?: boolean;
      windowWidth?: number;
    };
    jsPDF?: {
      unit?: "pt" | "mm" | "cm" | "in";
      format?: string | [number, number];
      orientation?: "portrait" | "landscape";
    };
    pagebreak?: {
      mode?: Array<"css" | "legacy" | "avoid-all">;
      before?: string | string[];
      after?: string | string[];
      avoid?: string | string[];
    };
  }

  interface Html2PdfWorker {
    set(opt: Html2PdfOptions): Html2PdfWorker;
    from(element: HTMLElement | string): Html2PdfWorker;
    save(): Promise<void>;
    toPdf(): Html2PdfWorker;
    outputPdf(type?: string): Promise<unknown>;
    then(onfulfilled?: (value: unknown) => unknown): Promise<unknown>;
  }

  function html2pdf(): Html2PdfWorker;
  export default html2pdf;
}
