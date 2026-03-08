// Copyright (c) 2026 V2 Software LLC. All rights reserved.

interface FormErrorProps {
  message?: string;
}

export function FormError({ message }: FormErrorProps) {
  if (!message) return null;
  return (
    <p className="text-sm text-red-500 mt-1" role="alert">
      {message}
    </p>
  );
}
