// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import * as Yup from "yup";

export const loginSchema = Yup.object({
  email: Yup.string()
    .email("Enter a valid email address.")
    .required("Email is required."),
  password: Yup.string().max(128, "Password is too long.").required("Password is required."),
});

export type LoginFormValues = Yup.InferType<typeof loginSchema>;

export const loginInitialValues: LoginFormValues = {
  email: "",
  password: "",
};

export const signupSchema = Yup.object({
  name: Yup.string().required("Name is required."),
  email: Yup.string()
    .email("Enter a valid email address.")
    .required("Email is required."),
  password: Yup.string()
    .min(8, "Password must be at least 8 characters.")
    .max(128, "Password is too long.")
    .required("Password is required."),
});

export type SignupFormValues = Yup.InferType<typeof signupSchema>;

export const signupInitialValues: SignupFormValues = {
  name: "",
  email: "",
  password: "",
};
