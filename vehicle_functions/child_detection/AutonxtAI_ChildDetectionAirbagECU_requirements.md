# AutonxtAI Child Presence Detection Airbag ECU - System Requirements

**Document type:** System Requirements Document  
**Version:** 1.0  
**Document status:** Draft  
**ID:** SYS-REQ-001  
**Title:** Child Presence Detection to Navigate Airbag ECU

## Requirement Summary

| Field | Content |
|---|---|
| ID | SYS-REQ-001 |
| Title | Child Presence Detection to Navigate Airbag ECU |
| Statement | The system shall detect the presence of a child seated in a child seat installed on the front passenger seat and deactivate the airbag based on driver decision. |
| Rationale | Prevent unsafe passenger airbag deployment. |
| Source | Autonxt AI - Safety concept |
| Verification | Test + analysis |
| Acceptance criteria | Airbag suppression status shall be transmitted to the airbag ECUs within 100 ms after confirmation of driver when child presenting. |

## Introduction

The purpose of this document is to define the system-level requirements for the Child Presence Detection (CPD) feature in the vehicle.

This document provides a structured and traceable specification of the expected system behavior, including functional and non-functional requirements, system interactions, and verification criteria. It serves as a reference for system design, implementation, integration, and validation activities.

The CPD feature supports multiple vehicle variants with different sensor configurations. The requirements defined in this document ensure consistent functional behavior across all supported variants while allowing configuration-specific capabilities.

## Scope

This document covers the requirements for detecting the presence of a child seated in a child seat installed on the front passenger seat and supporting the decision to suppress the passenger airbag when required.

The CPD feature is implemented across multiple vehicle variants with different sensor configurations.

### EV Basic Variant

- ISOFIX sensor
- Seat weight sensor

### EV Premium Variant

- Seat weight sensor
- Passenger monitoring camera (AI-based detection)

### EV Luxury Variant

- ISOFIX sensor
- Seat weight sensor
- Passenger monitoring camera (AI-based detection)

Despite differences in sensor configurations, all variants shall achieve the same functional objective of reliably detecting child presence and supporting safe airbag control.

### In Scope

- Detection of child presence using available sensor configurations
- Evaluation and confirmation of detection results
- Communication of detection status to the restraint system
- Interaction with driver input where applicable

### Out of Scope

- Detailed algorithm design, such as AI model implementation
- Hardware design of sensors and ECUs
- Low-level software implementation details

## References

The following documents are referenced and may contain additional requirements or constraints applicable to this specification:

- Child Detection Function Requirement from Kaizenics

## Terms, Definitions, and Abbreviations

| Term | Definition |
|---|---|
| CPD | Child Presence Detection |
| HMI | Human Monitoring Interface |

## System Context

The Child Presence Detection (CPD) system is part of the vehicle occupant monitoring and safety system.

The system:

- receives input from weight sensors and, where available, the passenger monitoring camera
- evaluates the available sensor information to determine child presence status
- transmits the detection result to the central computer unit to decide whether sending ignition signal to airbag ECUs
- may receive driver-related input where required by the vehicle concept

The CPD function supports multiple vehicle variants with different sensor availability. Depending on the variant, the function may use ISOFIX-related sensing, seat weight sensing, and camera-based occupant detection.

Within a zonal vehicle architecture, sensor data may be acquired by distributed zonal controllers and processed by a central compute unit. The resulting child presence status is provided to the airbag ECUs for passenger airbag control.

## Assumptions and Constraints

### Assumptions

- The CPD function is applicable to the front passenger seat.
- Required input signals are available according to the configured vehicle variant.
- The airbag ECUs interface is available.
- Driver confirmation input is available through the HMI.
- Variant coding is available to identify the implemented sensor configuration.

### Constraints

- The CPD function behavior depends on the sensor set available in the respective vehicle variant.
- The CPD function shall provide its output via the defined vehicle interface to the airbag ECUs.
- The CPD function shall support user confirmation as a mandatory condition for passenger airbag activation or deactivation.
- The CPD function shall comply with the applicable safety concept and legal requirements.
- Detailed sensor design and detailed detection algorithm design are outside the scope of this document.

## Functional Requirements

This section defines the functional behavior of the system.

Functional requirements describe what the system shall do, including:

- The system shall detect child presence on the front passenger seat.
- The system shall provide child presence status to the airbag ECUs.
- The system shall require driver confirmation before deactivating the front passenger airbag when child presence is detected.
- The system shall deactivate the front passenger airbag when child presence is detected and the driver confirms deactivation.

## Non-Functional Requirements

Non-functional requirements define constraints on system performance and quality attributes.

This includes:

- The system shall provide the required CPD output within 100 ms under defined operating conditions.
- The system shall achieve a child presence detection accuracy of at least 98% under defined operating conditions.
- The passenger monitoring camera shall provide coverage of the front passenger seat area, including the child seat space.
- The system shall detect loss or invalidity of required sensor inputs used for the CPD function.
- The system shall detect loss of communication required for the CPD function.
- The system shall report a fault status when the CPD function cannot operate as intended due to internal fault, sensor fault, or communication loss.
- The system shall enter a defined safe state when child presence detection cannot be performed reliably.

## Interface Requirements

This section defines the interfaces between the Child Presence Detection (CPD) system and related vehicle systems.

The CPD system shall interface with:

- Seat weight sensor
- ISOFIX sensor
- Passenger monitoring camera
- Airbag ECUs
- Touch-screen HMI

The interface communication shall be defined as follows:

- CAN shall be used for communication between the central computer, zonal ECU, airbag ECUs, cockpit ECU, seat weight sensor, and ISOFIX sensor.
- Ethernet shall be used for communication between the cockpit ECU and the touch-screen HMI.
- An automotive camera interface shall be used for communication between the passenger monitoring camera and the central computer.

The CPD system shall support the following interface interactions:

- The seat weight sensor and ISOFIX sensor shall provide input to the central computer through the zonal ECU.
- The passenger monitoring camera shall provide image data directly to the central computer for AI-based processing.
- The CPD system shall provide child detection status and confirmation request information to the cockpit system.
- The touch-screen HMI shall display child detection status and airbag confirmation request information to the driver.
- Driver confirmation input shall be provided from the touch-screen HMI via the cockpit system to the CPD system.
- The CPD system shall send the deactivation signal to airbag ECUs if receiving confirmation from driver.

The CPD-related interfaces shall define:

- signal availability
- data flow direction
- timing constraints
- logical interaction between connected systems

## Operating Modes and States

This section defines the operating modes and states relevant to the Child Presence Detection (CPD) system.

The CPD system shall support the following operating modes:

- Initialization
- Normal Operation
- Confirmation Pending
- Airbag Deactivation Active
- Fault / Degraded Operation

The operating modes shall be defined as follows:

### Initialization

The system starts up and checks the availability of required inputs and interfaces.

### Normal Operation

The system evaluates the available sensor inputs and determines the child presence status.

### Confirmation Pending

The system has detected child presence and is waiting for driver confirmation before deactivating the front passenger airbag.

### Airbag Deactivation Active

The system has received driver confirmation and has issued the corresponding deactivation status to the restraint controller.

### Fault / Degraded Operation

The system detects internal fault, sensor fault, or communication loss and cannot perform the CPD function as intended.

### State-Related Requirements

The CPD system behavior shall comply with the following state-related requirements:

- The system shall complete initialization before providing CPD output for airbag control.
- The system shall enter Normal Operation after successful initialization.
- The system shall enter Confirmation Pending when child presence is detected and airbag deactivation requires driver confirmation.
- The system shall enter Airbag Deactivation Active only after driver confirmation is received.
- The system shall not deactivate the front passenger airbag while the system is in Confirmation Pending.
- The system shall enter Fault / Degraded Operation when required inputs or communications are unavailable or invalid.
- The system shall provide the appropriate status output according to the active operating mode.
- The system shall transition to a defined safe state when the CPD function cannot be performed reliably.

## Fault Handling and Diagnostic Requirements

This section defines the fault handling and diagnostic requirements of the Child Presence Detection (CPD) system.

The CPD system shall support detection of the following fault conditions:

- loss of seat weight sensor input
- loss of ISOFIX sensor input
- loss of passenger monitoring camera input
- internal processing fault
- loss of communication required for the CPD function

The CPD system shall fulfill the following fault handling requirements:

- The system shall detect loss or invalidity of required sensor inputs used for the CPD function.
- The system shall detect loss of communication required for the CPD function.
- The system shall detect internal faults that prevent correct execution of the CPD function.
- The system shall report a fault status when the CPD function cannot operate as intended.
- The system shall transition to Fault / Degraded Operation when a relevant fault is detected.
- The system shall inhibit child presence detection output for airbag control when the CPD function cannot be performed reliably.
- The system shall maintain or transition to a defined safe state when a critical fault is detected.
- The system shall make diagnostic status available through the defined system interface.
- The system shall clear or update the reported fault status when the fault condition is no longer present, according to the defined diagnostic concept.

## Safety Requirements

This section defines the safety requirements of the Child Presence Detection (CPD) system.

The CPD system shall fulfill the following safety requirements:

- The system shall support safe passenger airbag control based on child presence detection status.
- The system shall require driver confirmation before deactivating the front passenger airbag when child presence is detected.
- The system shall not deactivate the front passenger airbag without driver confirmation when child presence is detected.
- The system shall provide child presence status to the driver only when the required inputs are available and valid.
- The system shall inhibit CPD output for airbag control when child presence detection cannot be performed reliably.
- The system shall transition to a defined safe state when a critical fault prevents correct execution of the CPD function.
- The system shall report a fault status when the CPD function cannot support the intended airbag-related function.
- The system shall ensure that invalid, unavailable, or inconsistent input data does not lead to unintended airbag deactivation.
- The system shall maintain traceable linkage between child presence detection status, driver confirmation, and airbag control output.

## Verification Strategy

This section defines the verification strategy for the Child Presence Detection (CPD) system requirements.

Each requirement defined in this document shall be verifiable by one or more of the following methods:

- Test
- Analysis
- Inspection
- Simulation

The verification strategy shall follow the principles below:

- Functional requirements shall be verified primarily by system test and integration test.
- Non-functional requirements shall be verified by test, analysis, or measurement, depending on the requirement type.
- Interface requirements shall be verified by inspection, interface test, and integration test.
- Operating modes and state transitions shall be verified by system test and state transition test.
- Fault handling and diagnostic requirements shall be verified by fault injection test, communication loss test, and diagnostic evaluation.
- Safety requirements shall be verified by test and analysis in accordance with the system safety concept.

Each requirement shall define or be associated with:

- a verification method
- corresponding acceptance criteria

## Traceability

All requirements shall be traceable across the development lifecycle.

Traceability shall include:

- Link to source requirements, such as safety concept or feature specification
- Link to system architecture elements
- Link to software/hardware components
- Link to verification artifacts, such as test cases and reports

This ensures consistency, completeness, and impact analysis capability.

## Document Status and Change Management

| No. | Document Version | Author | Reviewer | Date |
|---:|---|---|---|---|
| 1 | 1.0 | Le Chi Thien |  | Apr 17, 2026 |
