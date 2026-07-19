# This workspace (iam-automation-demo-prod) must be created manually in
# Terraform Cloud before `terraform init` here will succeed - see the
# "Environment promotion pattern" section of the root README.
terraform {
  cloud {
    organization = "jangus-iam-demo"

    workspaces {
      name = "iam-automation-demo-prod"
    }
  }
}
