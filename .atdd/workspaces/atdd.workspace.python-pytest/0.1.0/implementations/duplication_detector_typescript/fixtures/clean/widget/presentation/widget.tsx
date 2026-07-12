// Widget presentation component.
interface Props {
  label: string;
}

export function Widget(props: Props) {
  const label = props.label;
  return <div className="widget">{label}</div>;
}
