# ADR-0005: Keep Terraform state in a dedicated, versioned Azure storage account

**Status:** Accepted
**Date:** 2026-11-15

## Context

The Terraform in `infrastructure/homelab/` manages the three Proxmox VMs (ADR-0002). Its state
lived only in `terraform.tfstate` on the MacBook, which is gitignored and was not backed up. The
file maps each VM in the configuration to the real VM in Proxmox, and it carries sensitive
attributes for all three.

Losing that file would not stop the VMs. It would leave Terraform with no record of them. The
next `apply` would try to create three new VMs with the same IDs, and the only recovery would be
importing each one by hand.

Checking the state before moving it turned up a second problem. A `terraform plan` on 2026-11-15
proposed to destroy and recreate all three VMs. The base image is downloaded from Debian's
`latest` URL. A new upstream build changed its size, which forced the download resource to be
replaced, and every VM disk referenced it. One `apply` would have erased MLflow's database, the
k3s cluster and the metrics history.

## Decision

1. **Protect the VMs before anything else.**
   - The image download is set to `overwrite = false`, so the copy already on the host is kept.
   - Each VM ignores later changes to its base image and cloud-init, which only matter at
     creation.
   - `prevent_destroy` makes any plan that would destroy a VM fail.
   - After this, the plan showed no VM changes. The only change applied was the image resource's
     own `overwrite` flag.
2. **Move the state to an `azurerm` backend** in a storage account that holds nothing else:
   `homelab-tfstate-rg/homelabtfstateboom`, container `tfstate`, blob `homelab.tfstate`.
3. **Keep every version of the state.**
   - Blob versioning is on. Blob soft delete and container soft delete are set to 30 days.
   - Any earlier state can be downloaded by version ID, and a deleted one restored.
4. **Lock with the blob lease.** The backend takes a lease for the length of each plan or apply,
   so two runs cannot write the state at once.
5. **No key in the repository.** The backend looks up the account key through the operator's own
   `az login`. Running Terraform requires that login.
6. **The migration was verified.**
   - The copy in Azure has the same lineage and the same resources as the local file it
     replaced.
   - A plan with locking showed the same single pending change.
   - After that change was applied, a plan reported no changes.

## Alternatives considered

**A `tfstate` container in the existing `bankmldvcstore` account.**
- No new account would be needed.
- It lost because versioning is an account-wide setting. Turning it on there would also version
  every DVC and MLflow artifact write.
- It would also put the infrastructure's state behind the same keys as BankML's data, which the
  backup SAS and the Container App already use.

**Commit the state to the repository, encrypted.**
- The history would be in Git.
- It lost because it gives no locking.
- It also makes every `apply` a commit, and puts sensitive attributes, even encrypted, into a
  public repository's history permanently.

**Terraform Cloud's free tier.**
- Locking and history are built in.
- It lost because it adds a third-party account and token for a single state file of 23 KB.
- Azure already holds the lab's other state, and the operator is already logged in to it.

**Keep the state local and back up the file.**
- This is the smallest change.
- It lost because it does not lock, and it still ties Terraform to one machine.

## Consequences

- **Terraform is no longer tied to the MacBook.** Any machine with `az login` to the subscription
  can plan and apply.
- **A bad apply can be undone at the state level**, by restoring an earlier version.
- **Rebuilding a VM takes a deliberate code change.** `prevent_destroy` has to be removed first,
  which is the intent. `terraform destroy` is refused until then.
- **New Debian images no longer reach existing VMs through Terraform.** Updates come from the
  guests' own package updates. A new VM is still built from whichever image is on the host.
- **The subscription is Azure for Students.** If it lapses, the state account goes with it.
  Moving the state is `terraform init -migrate-state` to another backend.
