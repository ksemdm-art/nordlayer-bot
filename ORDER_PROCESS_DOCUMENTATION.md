# Telegram Bot Order Process Implementation

## Overview

This document describes the implementation of the step-by-step order process for the NordLayer 3D printing platform Telegram bot. The implementation fulfills task 7.3 requirements by providing a complete order workflow with state management, validation, and user-friendly navigation.

## Architecture

### Core Components

1. **OrderHandlers** (`order_handlers.py`) - Main order processing logic
2. **SessionManager** (`session_manager.py`) - User session state management  
3. **OrderSession** - Data class for storing order information
4. **OrderStep** - Enum defining order process steps

### State Machine

The order process follows a linear state machine with the following steps:

```
START → SERVICE_SELECTION → CONTACT_INFO → FILE_UPLOAD → 
SPECIFICATIONS → DELIVERY → CONFIRMATION → COMPLETED
```

Each step can navigate back to previous steps for editing.

## Implementation Details

### 1. State Machine with OrderStep Enum

```python
class OrderStep(Enum):
    START = "start"
    SERVICE_SELECTION = "service_selection"
    CONTACT_INFO = "contact_info"
    FILE_UPLOAD = "file_upload"
    SPECIFICATIONS = "specifications"
    DELIVERY = "delivery"
    CONFIRMATION = "confirmation"
    COMPLETED = "completed"
```

### 2. Contact Information Collection

**Features:**
- Sequential collection: Name → Email → Phone (optional)
- Real-time validation for each field
- Option to skip phone number
- Edit capabilities at any step

**Validation Rules:**
- **Name**: 2-50 characters, letters/spaces/hyphens/apostrophes only
- **Email**: Standard email format validation
- **Phone**: Optional, international format support

### 3. File Upload Handling

**Supported Formats:** `.stl`, `.obj`, `.3mf`
**Size Limit:** 50MB per file
**Features:**
- Multiple file upload support
- File validation (format and size)
- Integration with backend API via `APIClient.upload_file()`
- File removal capability
- Progress feedback to user

**Error Handling:**
- Invalid format detection
- File size limit enforcement
- Upload failure recovery
- Network error handling

### 4. Printing Specifications Selection

**Material Options:**
- PLA (базовый) - Basic material
- PETG (прочный) - Durable material  
- ABS (термостойкий) - Heat-resistant material
- TPU (гибкий) - Flexible material

**Quality Options:**
- Черновое (0.3мм) - Draft quality, fast printing
- Стандартное (0.2мм) - Standard quality
- Высокое (0.1мм) - High quality, slow printing

**Infill Options:**
- 15% - Light model
- 30% - Standard strength
- 50% - Strong model
- 100% - Maximum strength

### 5. Delivery Options

**Pickup (Самовывоз):**
- Free option
- No additional information required

**Shipping (Доставка):**
- Requires full address input
- Address validation (minimum 10 characters)
- Stored in `delivery_details` field

### 6. Order Confirmation

**Features:**
- Complete order summary display
- Edit menu for modifying any section
- Final validation before submission
- Order creation via API integration

**Summary Includes:**
- Customer contact information
- Selected service
- Uploaded files count
- Printing specifications
- Delivery method and details

### 7. Navigation System

**Back Navigation:**
- Each step provides "back" buttons
- Previous step data is preserved
- Allows editing without losing progress

**Edit Menu:**
- Accessible from confirmation step
- Direct navigation to any section
- Maintains order state consistency

## API Integration

### Order Creation
```python
order_data = {
    "customer_name": session.customer_name,
    "customer_email": session.customer_email,
    "customer_phone": session.customer_phone,
    "service_id": session.service_id,
    "source": "TELEGRAM",
    "specifications": {
        "material": "pla",
        "quality": "standard", 
        "infill": "30",
        "files_info": session.files
    },
    "delivery_needed": "true/false",
    "delivery_details": session.delivery_details
}
```

### File Upload
- Files are uploaded immediately when received
- Upload results stored in session for order creation
- Supports multiple file formats and proper error handling

## User Experience Features

### Inline Keyboards
- All interactions use inline keyboards for better UX
- Context-aware button options
- Clear navigation paths

### Progress Indicators
- Step-by-step guidance
- Clear current status indication
- Progress preservation across sessions

### Error Handling
- User-friendly error messages
- Automatic retry suggestions
- Graceful degradation on failures

### Validation Feedback
- Real-time input validation
- Clear error descriptions
- Guidance for correct input format

## Session Management

### Session Lifecycle
1. **Creation**: New session on order start
2. **Updates**: Progressive data collection
3. **Validation**: Continuous data validation
4. **Completion**: Order submission and cleanup
5. **Cleanup**: Automatic session removal

### Data Persistence
- In-memory storage during order process
- Automatic cleanup after completion
- Session timeout handling (24 hours)

### Session Data Structure
```python
@dataclass
class OrderSession:
    user_id: int
    step: OrderStep
    service_id: Optional[int]
    service_name: Optional[str]
    customer_name: Optional[str]
    customer_email: Optional[str]
    customer_phone: Optional[str]
    files: List[Dict[str, Any]]
    specifications: Dict[str, Any]
    delivery_needed: Optional[bool]
    delivery_details: Optional[str]
    created_at: datetime
```

## Error Handling Strategy

### API Errors
- Network connectivity issues
- Server response errors
- File upload failures
- Service unavailability

### Validation Errors
- Input format validation
- Required field checking
- File format/size validation
- Address validation

### Session Errors
- Session not found
- Session expiration
- Invalid step transitions
- Data corruption

## Testing

### Test Coverage
- Session management functionality
- Validation functions
- Order step flow logic
- Data conversion and serialization

### Test Results
```
✅ Session creation and updates
✅ Input validation (name, email, phone)
✅ Order step progression
✅ Data conversion for API
✅ Session cleanup
```

## Integration Points

### Main Bot Integration
- Command handlers (`/order`)
- Callback query routing
- Text message processing
- File upload handling

### Backend API Integration
- Service catalog fetching
- File upload endpoints
- Order creation endpoints
- Error response handling

## Security Considerations

### Data Validation
- All user inputs are validated
- File type and size restrictions
- Email format verification
- Phone number sanitization

### Session Security
- User-specific session isolation
- Automatic session cleanup
- No persistent storage of sensitive data

## Performance Considerations

### Memory Management
- Efficient session storage
- Automatic cleanup of old sessions
- Minimal memory footprint per session

### Network Optimization
- Efficient API calls
- File upload optimization
- Error retry mechanisms

## Future Enhancements

### Potential Improvements
1. **Persistent Session Storage** - Redis integration for session persistence
2. **Advanced File Processing** - STL file preview and analysis
3. **Price Calculation** - Real-time cost estimation
4. **Order Templates** - Save and reuse common orders
5. **Batch Operations** - Multiple file processing optimization

### Scalability Considerations
- Database session storage for high load
- Distributed file storage
- Load balancing for API calls
- Caching for service catalog

## Conclusion

The order process implementation successfully fulfills all requirements from task 7.3:

✅ **State machine with OrderStep enum** - Complete step-by-step workflow
✅ **Contact information collection** - Name, email, phone with validation  
✅ **File upload handling** - Format/size validation, API integration
✅ **Printing specifications** - Material, quality, infill selection
✅ **Delivery options** - Pickup/shipping with address collection
✅ **Order confirmation** - Complete summary with edit capabilities
✅ **Navigation system** - Back/forward navigation between steps

The implementation provides a robust, user-friendly order process that integrates seamlessly with the existing bot architecture and backend API.