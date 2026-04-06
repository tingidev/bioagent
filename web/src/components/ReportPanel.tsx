interface Props {
  report: string;
}

export default function ReportPanel({ report }: Props) {
  return (
    <div className="border-t border-bio-border p-6 overflow-y-auto flex-1">
      <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">
        Findings
      </h3>
      <div className="prose prose-invert prose-sm max-w-none text-gray-300 leading-relaxed whitespace-pre-wrap">
        {report}
      </div>
    </div>
  );
}
