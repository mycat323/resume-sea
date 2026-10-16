function print() {
  // 用相对当前页面的地址打开打印页。
  // 不能写死 "/print"：站点发布在 /<repo>/docs/<name>/ 子路径下，
  // 绝对路径会解析到域名根而 404。
  const printURL = new URL("print", window.location.href).href;
  const printWindow = window.open(printURL, "_blank");
  if (!printWindow) return; // 被浏览器拦截弹窗时不报错
  printWindow.onload = function () {
    printWindow.print();
    // Close the print window after a delay
    setTimeout(() => printWindow.close(), 500);
  };
}

function generatePDF() {
  if (typeof html2pdf === "undefined") {
    alert("PDF 组件尚未加载完成，请稍后再试");
    return;
  }
  // Get the print layout URL
  const printURL = new URL("print", window.location.href).href;

  // Fetch the print layout content
  fetch(printURL)
    .then((response) => response.text())
    .then((html) => {
      // Create a temporary container
      const container = document.createElement("div");
      container.innerHTML = html;

      // Get name from the DOM (as defined in data.yml)
      const name = document.querySelector(".name").textContent;
      // Format filename: replace spaces with underscores and append _resume.pdf
      const filename = `${name.replace(/\s+/g, "_")}_Resume.pdf`;

      // Configure pdf options
      const opt = {
        margin: 10,
        filename: filename,
        image: { type: "jpeg", quality: 0.98 },
        html2canvas: {
          scale: 2,
          useCORS: true,
          letterRendering: true,
        },
        jsPDF: {
          unit: "mm",
          format: "a4",
          orientation: "portrait",
        },
      };

      // Generate PDF
      html2pdf()
        .set(opt)
        .from(container)
        .save()
        .catch((err) => console.error("Error generating PDF:", err));
    })
    .catch((err) => console.error("Error fetching print layout:", err));
}
