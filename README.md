# frey
Frey - NetDevOps in a Box

Frey is a NetDevOps Distribution designed to streamline NetDevOps tooling installation and configuration, allowing network engineers to take advantage of DevOps concepts quickly and easily.

Getting started with NetDevOps can be overwhelming, given the plethora of bespoke tools and technologies available.  Many engineers find themselves struggling to get started because the process of identifying the tools required and the subsequent configuration and integration of said tools requires deep knowledge of each tool, solid understanding of operating systems and virtualization concepts, container and container orchestration paradigms, CI/CD pipelines, network simulations, linting, and more.  Frey helps ease this barrier to entry.

Frey is highly opinionated in its tool selection.  The project maintainers select the tools included in the distribution based on the following criteria:
 - Open source and freely available (wherever possible)
 - Popularity within the community
 - Ease of use

The Frey Project's goal is to integrate popular DevOps tools together in a seamless manner for ease of implementation and day to day usage.  Frey is NOT intended to create new NetDevOps tools or reimagine fundamental concepts.  Rather, Frey's goal is to build on the work of others and embrace common practice and de facto standards and tooling wherever possible. 

## Network Automation Phases and Technology Selections

Many different paradigms exist for codifying the conceptual stages of the NetDevOps lifecycle and there is no "correct" answer.  The Frey Project breaks down NetDevOps in to the following stages:

 - Source(s) of Truth
 - Config Automation & Orchestration
 - The Network
 - Pipelines, Testing & Quality Control
 - Simulation
 - Observability / Assurance

Appropriate tools must be selected for each of these stages, based on the criteria listed above.  Care must be taken in not selecting too many tools for each stage, as the complexity of integrating the various tools together grows as the number of possible combinations increases.

The following table identifies technologies that the Frey project is evaluating for its distribution.

| Source(s) of Truth | Config Automation & Orchestration | The Network | Pipelines, Testing & Quality Control | Simulation | Observability / Assurance | 
| ------------------ | -------------------------- | ---------------- | ---------- | --------- | ------------------------------ | 
| NetBox<br/>Nautobot<br/>Ansible Vault | Ansible<br/>Python | Cisco<br/>Arista<br/>Juniper | gitlab<br/>github actions<br/>pybatfish<br/>pyATS<br/>ANTA<br/>pytest | netlab<br/>containerlab | icinga<br/>prometheus<br/>grafana<br/>LibreNMS<br/><i>need log solution</i> | 

## Approach & Implementation Plan
 - Use publicly available containers wherever possible
 - Assume a brownfield implementation wherever possible
 - Simulation stage is likely the most complicated and expensive.  Do it last and make it an optional step.
 - Observability space is complex and will likely be time consuming.  Focus on the value-add stuff first (SoT, config orchestration, automated testing and complete the feedback loop)
 - End goal of this effort is a single, standalone artifact (bash script, python script, helm chart, whatever) that quickly and easily sets up this system
 - 80/20 approach; focus on covering the most common and most basic scenarios first.
 - Where does the end user's git repo live? Will build a local git repo as part of Frey's early iterations to stay true to the "NetDevOps in a box" goal, but will most assuredly need to support user configurable external repos.  What does this do to the pipeline infrastructure?  TBD...

1. Stand up NetBox
 - Seed inventory
 - Use docker image
 - Find way to back up & restore data
 - Investigate autodiscovery options
 - Investigate secrets management
2. Stand up AWX
 - Use docker image
 - Leverage Netbox as dynamic inventory for AWX
 - Find way to back up and restore data
 - Investigate how NetBox inventory fields are manifested in AWX/ansible
 - Write simple playbook against virtual/lab device(s) to verify basic functionality
 - Write simple Jinja template and push against virtual/lab device(s)
 - Demonstrate "compliance" checks of template vs actual state
   
