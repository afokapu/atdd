// Button presentation component.
interface ButtonProps {
  text: string;
  id: string;
}

export function Button(props: ButtonProps) {
  return <button id={props.id} type="button">{props.text}</button>;
}
