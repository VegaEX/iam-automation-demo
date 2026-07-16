terraform {
  cloud {
    organization = "jangus-iam-demo"

    workspaces {
      name = "jangus-iam-demo"
    }
  }
}
